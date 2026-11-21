"""Ask Reede before a tool runs. Fail closed: anything but an explicit allow raises ReedeDenied."""
import asyncio
import copy
import functools
import hashlib
import inspect
import json
import os
import urllib.request

from . import DEFAULT_ENDPOINT


class ReedeDenied(Exception):
    """The tool must not run. `decision` is "deny", "needs_approval", or "deny" for an unavailable check."""

    def __init__(self, decision, reason=None, approval_id=None, receipt_id=None):
        self.decision = decision
        self.reason = reason
        self.approval_id = approval_id
        self.receipt_id = receipt_id
        super().__init__(f"Reede {decision}" + (f": {reason}" if reason else ""))


def _digest(args):
    # Sorted keys and compact separators: the same value hashes the same in Python and JS.
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _trace_ids():
    try:
        from opentelemetry import trace
    except ImportError:
        return {}
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return {}
    return {"trace_id": format(ctx.trace_id, "032x"), "span_id": format(ctx.span_id, "016x")}


def check(name, *, kind="tool", target_host=None, args=None, est_credits=None, endpoint=None, headers=None, timeout=5):
    """Ask Reede whether `name` may run. Returns the response dict on allow, raises ReedeDenied otherwise."""
    body = {"kind": kind, "name": name}
    if target_host is not None:
        body["target_host"] = target_host
    if args is not None:
        body["args_digest"] = _digest(args)
    if est_credits is not None:
        body["est_credits"] = est_credits
    body.update(_trace_ids())

    base = (endpoint or os.environ.get("REEDE_OTLP_ENDPOINT") or DEFAULT_ENDPOINT).rstrip("/")
    token = os.environ.get("REEDE_TOKEN")
    if headers is None:
        headers = {"authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(
        f"{base}/api/v1/reede/check",
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json", **headers},
        method="POST",
    )
    try:
        # urlopen raises on network errors, timeouts and HTTP status >= 400.
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            if not 200 <= resp.status < 300:
                raise ReedeDenied("deny", f"check unavailable: HTTP {resp.status}")
            raw = resp.read()
    except ReedeDenied:
        raise
    except Exception as e:
        raise ReedeDenied("deny", f"check unavailable: {e}") from e

    try:
        result = json.loads(raw)
        decision = result["decision"]
    except Exception as e:
        raise ReedeDenied("deny", f"check unavailable: bad response: {e}") from e
    if decision == "allow":
        return result
    if decision != "needs_approval":
        decision = "deny"
    raise ReedeDenied(
        decision,
        result.get("reason"),
        approval_id=result.get("approval_id"),
        receipt_id=result.get("receipt_id"),
    )


def guard(fn=None, *, name=None, kind="tool", target_host=None, est_credits=None, endpoint=None, headers=None, timeout=5):
    """Decorator: call Reede before a sync or async function. Raises ReedeDenied unless allowed."""
    options = dict(kind=kind, target_host=target_host, est_credits=est_credits,
                   endpoint=endpoint, headers=headers, timeout=timeout)

    def decorate(f):
        tool_name = name or f.__name__

        if inspect.iscoroutinefunction(f):
            @functools.wraps(f)
            async def guarded_async(*args, **kwargs):
                # check() blocks on HTTP, so run it off the event loop.
                await asyncio.to_thread(check, tool_name, args={"args": args, "kwargs": kwargs}, **options)
                return await f(*args, **kwargs)
            return guarded_async

        @functools.wraps(f)
        def guarded(*args, **kwargs):
            check(tool_name, args={"args": args, "kwargs": kwargs}, **options)
            return f(*args, **kwargs)
        return guarded

    return decorate if fn is None else decorate(fn)


def guard_langchain_tool(tool, *, name=None, target_host=None, est_credits=None, endpoint=None, headers=None, timeout=5):
    """Return a copy of a LangChain BaseTool whose invoke/ainvoke ask Reede first.

    Duck-typed: no LangChain import. The copy stays a BaseTool subclass, so it works in
    Deep Agents' `tools=[...]`. The original tool is not modified.
    """
    tool_name = name or getattr(tool, "name", None) or type(tool).__name__
    options = dict(kind="tool", target_host=target_host, est_credits=est_credits,
                   endpoint=endpoint, headers=headers, timeout=timeout)
    base = type(tool)

    def _args(input):
        # ToolNode passes a tool call dict; hash its arguments, not the call id.
        if isinstance(input, dict) and input.get("type") == "tool_call":
            return input.get("args")
        return input

    def invoke(self, input, config=None, **kwargs):
        check(tool_name, args=_args(input), **options)
        return base.invoke(self, input, config, **kwargs)

    async def ainvoke(self, input, config=None, **kwargs):
        await asyncio.to_thread(check, tool_name, args=_args(input), **options)
        return await base.ainvoke(self, input, config, **kwargs)

    guarded = tool.model_copy() if hasattr(tool, "model_copy") else copy.copy(tool)
    guarded.__class__ = type(base.__name__, (base,), {"invoke": invoke, "ainvoke": ainvoke})
    return guarded
