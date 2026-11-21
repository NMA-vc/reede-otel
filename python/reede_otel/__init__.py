"""Point an OpenTelemetry-instrumented Python agent at Reede. One function, nothing else."""
import os

DEFAULT_ENDPOINT = "http://127.0.0.1:4318"


def configure(endpoint=None, token=None):
    """Set the standard OTLP env vars so any OTel exporter created afterwards talks to Reede.

    Call it before importing langchain/langgraph/langsmith. `endpoint` is the base URL
    (exporters append /v1/traces); it falls back to REEDE_OTLP_ENDPOINT, then the local
    `reede serve` address. `token` (or REEDE_TOKEN) adds a bearer header for a hosted
    endpoint; local `reede serve` needs none. Returns the endpoint used.
    """
    endpoint = (endpoint or os.environ.get("REEDE_OTLP_ENDPOINT") or DEFAULT_ENDPOINT).rstrip("/")
    token = token or os.environ.get("REEDE_TOKEN")
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = endpoint
    os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
    # Non-empty headers also stop LangSmith's OTel mode from adding an x-api-key header.
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"authorization=Bearer {token}" if token else "x-reede=1"
    # LangSmith: export OTLP only, nothing to LangSmith.
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_TRACING_MODE", "otel")
    return endpoint


# Imported last: guard.py reads DEFAULT_ENDPOINT from this package.
from .guard import ReedeDenied, check, guard, guard_langchain_tool  # noqa: E402

__all__ = ["configure", "check", "guard", "guard_langchain_tool", "ReedeDenied", "DEFAULT_ENDPOINT"]
