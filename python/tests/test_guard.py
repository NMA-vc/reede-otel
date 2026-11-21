import asyncio
import hashlib
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from reede_otel import ReedeDenied, check, guard


class Stub:
    """A local stand-in for `reede serve`: answers POST /api/v1/reede/check with a fixed reply."""

    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body or {}
        self.seen = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("content-length", 0)))
                stub.seen.append({"path": self.path, "headers": dict(self.headers), "body": json.loads(raw)})
                data = json.dumps(stub.body).encode()
                self.send_response(stub.status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.endpoint = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.delenv("REEDE_TOKEN", raising=False)
    servers = []

    def make(status=200, body=None):
        s = Stub(status, body)
        servers.append(s)
        return s

    yield make
    for s in servers:
        s.close()


def dead_endpoint():
    """A base URL with nothing listening: the connection is refused."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


def test_allow_runs_tool(stub):
    s = stub(body={"decision": "allow", "receipt_id": "r1"})
    ran = []

    @guard(endpoint=s.endpoint)
    def lookup(topic):
        ran.append(topic)
        return f"fact about {topic}"

    assert lookup("receipts") == "fact about receipts"
    assert ran == ["receipts"]
    sent = s.seen[0]
    assert sent["path"] == "/api/v1/reede/check"
    assert sent["body"]["kind"] == "tool"
    assert sent["body"]["name"] == "lookup"
    assert len(sent["body"]["args_digest"]) == 64


def test_deny_raises_and_does_not_run(stub):
    s = stub(body={"decision": "deny", "reason": "not on the allowlist", "receipt_id": "r2"})
    ran = []

    @guard(endpoint=s.endpoint)
    def send_mail():
        ran.append(True)

    with pytest.raises(ReedeDenied) as info:
        send_mail()
    assert info.value.decision == "deny"
    assert info.value.reason == "not on the allowlist"
    assert info.value.receipt_id == "r2"
    assert ran == []


def test_needs_approval_raises_with_approval_id(stub):
    s = stub(body={"decision": "needs_approval", "reason": "over threshold", "approval_id": "ap-7", "receipt_id": "r3"})
    with pytest.raises(ReedeDenied) as info:
        check("transfer", endpoint=s.endpoint)
    assert info.value.decision == "needs_approval"
    assert info.value.approval_id == "ap-7"


def test_server_down_fails_closed(monkeypatch):
    monkeypatch.delenv("REEDE_TOKEN", raising=False)
    ran = []

    @guard(endpoint=dead_endpoint(), timeout=2)
    def lookup():
        ran.append(True)

    with pytest.raises(ReedeDenied) as info:
        lookup()
    assert info.value.decision == "deny"
    assert info.value.reason.startswith("check unavailable")
    assert ran == []


def test_non_2xx_fails_closed(stub):
    s = stub(status=500, body={"decision": "allow"})
    ran = []

    @guard(endpoint=s.endpoint)
    def lookup():
        ran.append(True)

    with pytest.raises(ReedeDenied) as info:
        lookup()
    assert info.value.reason.startswith("check unavailable")
    assert ran == []


def test_unknown_decision_is_denied(stub):
    s = stub(body={"decision": "maybe"})
    with pytest.raises(ReedeDenied) as info:
        check("lookup", endpoint=s.endpoint)
    assert info.value.decision == "deny"


def test_async_guard(stub):
    s = stub(body={"decision": "allow"})

    @guard(endpoint=s.endpoint)
    async def lookup(x):
        return x + 1

    assert asyncio.run(lookup(1)) == 2


def test_async_guard_denied_does_not_run(stub):
    s = stub(body={"decision": "deny"})
    ran = []

    @guard(endpoint=s.endpoint)
    async def lookup():
        ran.append(True)

    with pytest.raises(ReedeDenied):
        asyncio.run(lookup())
    assert ran == []


def test_args_digest_is_stable_across_key_order(stub):
    s = stub(body={"decision": "allow"})
    check("t", args={"b": 1, "a": {"y": 2, "x": [1, 2]}}, endpoint=s.endpoint)
    check("t", args={"a": {"x": [1, 2], "y": 2}, "b": 1}, endpoint=s.endpoint)
    first, second = (sent["body"]["args_digest"] for sent in s.seen)
    assert first == second
    # Fixed vector, shared with the JS test: sha256 of the canonical JSON '{"a":2,"b":1}'.
    check("t", args={"b": 1, "a": 2}, endpoint=s.endpoint)
    assert s.seen[2]["body"]["args_digest"] == hashlib.sha256(b'{"a":2,"b":1}').hexdigest()


def test_bearer_token_from_env_on_hosted_endpoint(stub, monkeypatch):
    monkeypatch.setenv("REEDE_TOKEN", "t0k")
    s = stub(body={"decision": "allow"})
    check("t", endpoint=s.endpoint)
    headers = {k.lower(): v for k, v in s.seen[0]["headers"].items()}  # urllib capitalizes names
    assert headers["authorization"] == "Bearer t0k"


class FakeTool:
    """Shaped like a LangChain BaseTool for the parts guard_langchain_tool touches."""

    name = "lookup"
    calls = []

    def invoke(self, input, config=None, **kwargs):
        self.calls.append(("invoke", input))
        return "sync"

    async def ainvoke(self, input, config=None, **kwargs):
        self.calls.append(("ainvoke", input))
        return "async"


def test_langchain_tool_guard_checks_before_invoke(stub):
    from reede_otel.guard import guard_langchain_tool

    s = stub(body={"decision": "allow"})
    FakeTool.calls = []
    original = FakeTool()
    guarded = guard_langchain_tool(original, endpoint=s.endpoint)
    assert guarded.invoke({"topic": "x"}) == "sync"
    assert asyncio.run(guarded.ainvoke({"topic": "y"})) == "async"
    assert s.seen[0]["body"]["name"] == "lookup"
    assert FakeTool.calls == [("invoke", {"topic": "x"}), ("ainvoke", {"topic": "y"})]
    assert type(original) is FakeTool  # the original is untouched


def test_langchain_tool_guard_denied_does_not_invoke(stub):
    from reede_otel.guard import guard_langchain_tool

    s = stub(body={"decision": "deny", "reason": "no"})
    FakeTool.calls = []
    guarded = guard_langchain_tool(FakeTool(), endpoint=s.endpoint)
    with pytest.raises(ReedeDenied):
        guarded.invoke({"topic": "x"})
    with pytest.raises(ReedeDenied):
        asyncio.run(guarded.ainvoke({"topic": "x"}))
    assert FakeTool.calls == []


def test_langchain_real_base_tool(stub):
    pytest.importorskip("langchain_core")
    from langchain_core.tools import tool as lc_tool
    from reede_otel.guard import guard_langchain_tool

    @lc_tool
    def lookup(topic: str) -> str:
        """Look up a fact."""
        return f"fact:{topic}"

    s = stub(body={"decision": "allow"})
    guarded = guard_langchain_tool(lookup, endpoint=s.endpoint)
    assert guarded.invoke({"topic": "x"}) == "fact:x"
    # ToolNode-style tool call: the digest covers the arguments, not the call id.
    message = guarded.invoke({"name": "lookup", "args": {"topic": "x"}, "id": "c1", "type": "tool_call"})
    assert message.content == "fact:x"
    assert s.seen[0]["body"]["args_digest"] == s.seen[1]["body"]["args_digest"]
    s.body = {"decision": "deny"}
    with pytest.raises(ReedeDenied):
        guarded.invoke({"topic": "x"})
