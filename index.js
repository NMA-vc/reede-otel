// Options for an OTLP exporter pointed at Reede. One function, no dependencies.
export const DEFAULT_ENDPOINT = 'http://127.0.0.1:4318';

/**
 * Returns { endpoint, headers } to pass to an OTLP exporter (e.g. Mastra's OtelExporter
 * `provider.custom`). `endpoint` is the base URL: OTLP/HTTP exporters append /v1/traces.
 * Falls back to REEDE_OTLP_ENDPOINT, then local `reede serve`. `token` (or REEDE_TOKEN)
 * adds a bearer header for a hosted endpoint; local `reede serve` needs none.
 */
export function reedeOtel({ endpoint, token } = {}) {
  const base = (endpoint ?? process.env.REEDE_OTLP_ENDPOINT ?? DEFAULT_ENDPOINT).replace(/\/+$/, '');
  const bearer = token ?? process.env.REEDE_TOKEN;
  return { endpoint: base, headers: bearer ? { authorization: `Bearer ${bearer}` } : {} };
}
