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

Apache-2.0. See [github.com/NMA-vc/reede-otel](https://github.com/NMA-vc/reede-otel).
