# reede-otel

Point an OpenTelemetry agent at [Reede](https://github.com/NMA-vc/reede). One function per
language, nothing more: it sets the OTLP endpoint (default `http://127.0.0.1:4318`, the address
of `reede serve`) and, optionally, a bearer header for a hosted endpoint.

A hosted Reede endpoint is coming; local `reede serve` needs no token.

**Not published to PyPI or npm yet.** Install from this repository.

## Python (`python/`)

```text
pip install "reede-otel @ git+https://github.com/NMA-vc/reede-otel#subdirectory=python"
```

```python
import reede_otel
reede_otel.configure()   # before importing langchain / langgraph / langsmith
```

It sets `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL` and
`OTEL_EXPORTER_OTLP_HEADERS`, and defaults `LANGSMITH_TRACING=true` and
`LANGSMITH_TRACING_MODE=otel` (LangSmith's OpenTelemetry mode; nothing goes to LangSmith).
Arguments: `configure(endpoint=None, token=None)`; fallbacks `REEDE_OTLP_ENDPOINT`, `REEDE_TOKEN`.

## npm (repository root)

```text
npm install github:NMA-vc/reede-otel
```

```js
import { reedeOtel } from '@reede/otel';
const { endpoint, headers } = reedeOtel();   // { endpoint, token } optional
// Mastra: new OtelExporter({ provider: { custom: { endpoint, headers, protocol: 'http/protobuf' } } })
```

Returns `{ endpoint, headers }` for any OTLP/HTTP exporter. `endpoint` is a base URL; exporters
append `/v1/traces`.

## Guard (npm): ask Reede before a tool runs (opt-in)

Reede answers `POST {endpoint}/api/v1/reede/check` with `allow`, `deny` or `needs_approval`.
The guard calls it before the tool runs and throws `ReedeDenied` unless the answer is `allow`.

```js
import { withReedeGuard, check, ReedeDenied } from '@reede/otel';
const tool = withReedeGuard(myMastraTool);   // wraps tool.execute; the original is untouched
// or, for any call: await check('send_email', { kind: 'tool', args: { to } });
```

`ReedeDenied` carries `decision`, `reason`, `approvalId` and `receiptId`. Options: `kind`,
`targetHost`, `estCredits`, `endpoint`, `headers`, `timeout` (seconds, default 5), `name`.

**Fail closed by design.** A network error, a timeout, a non-2xx response or an unreadable answer
throws `ReedeDenied` with `decision: 'deny'` and `reason: 'check unavailable: ...'`. The tool does
not run. Reede being down stops the tool; it never lets it through.

## Tests

```text
npm test
cd python && pip install pytest . && pytest tests
```

Apache-2.0.
