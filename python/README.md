# reede-otel

Point an OpenTelemetry-instrumented Python agent at [Reede](https://github.com/NMA-vc/reede).
One function, nothing else: it sets the standard OTLP environment variables so every exporter
created afterwards sends to `reede serve` (default `http://127.0.0.1:4318`), or to a hosted
Reede endpoint with a bearer token.

```bash
pip install reede-otel
```

```python
import reede_otel
reede_otel.configure()   # call before importing langchain / langgraph / langsmith
```

`configure(endpoint=None, token=None)` sets `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_EXPORTER_OTLP_PROTOCOL` (`http/protobuf`) and `OTEL_EXPORTER_OTLP_HEADERS`, and defaults
`LANGSMITH_TRACING=true` and `LANGSMITH_TRACING_MODE=otel` (OpenTelemetry mode only; nothing is
sent to LangSmith). Fallbacks: `REEDE_OTLP_ENDPOINT`, then `REEDE_TOKEN`. It returns the endpoint used.

## Guard (Python): ask Reede before a tool runs (opt-in)

Reede answers `POST {endpoint}/api/v1/reede/check` with `allow`, `deny` or `needs_approval`.
The guard calls it before the tool runs and raises `ReedeDenied` unless the answer is `allow`.

```python
from reede_otel import guard, check, ReedeDenied

@guard                     # sync or async function
def send_email(to): ...

# LangChain / Deep Agents: wrap the tool, pass the copy to create_deep_agent(tools=[...])
from reede_otel import guard_langchain_tool
agent = create_deep_agent(model=..., tools=[guard_langchain_tool(lookup)])
```

`ReedeDenied` carries `decision`, `reason`, `approval_id` and `receipt_id`. Options on
`guard`, `check` and `guard_langchain_tool`: `name`, `kind`, `target_host`, `est_credits`,
`endpoint`, `headers`, `timeout` (seconds, default 5). The endpoint falls back to
`REEDE_OTLP_ENDPOINT` then `http://127.0.0.1:4318`; the bearer token to `REEDE_TOKEN`.
Arguments are hashed (sha256 over sorted, compact JSON) into `args_digest`; the arguments
themselves are never sent. `trace_id`/`span_id` come from the current OpenTelemetry span when
`opentelemetry` is importable.

**Fail closed by design.** A network error, a timeout, a non-2xx response or an unreadable answer
raises `ReedeDenied` with `decision="deny"` and `reason="check unavailable: ..."`. The tool does
not run. Reede being down stops the tool; it never lets it through.

Apache-2.0. See [github.com/NMA-vc/reede-otel](https://github.com/NMA-vc/reede-otel).
