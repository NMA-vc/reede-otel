// Options for an OTLP exporter pointed at Reede, plus an opt-in guard that asks Reede before a
// tool runs. No dependencies.
import { createHash } from 'node:crypto';

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

/** Thrown when Reede does not allow a tool call, or when Reede cannot be reached (fail closed). */
export class ReedeDenied extends Error {
  constructor(decision, reason, { approvalId, receiptId } = {}) {
    super(`Reede ${decision}${reason ? `: ${reason}` : ''}`);
    this.name = 'ReedeDenied';
    this.decision = decision;
    this.reason = reason;
    this.approvalId = approvalId;
    this.receiptId = receiptId;
  }
}

// Sorted keys at every depth, compact: the same value hashes the same in Python and JS.
const canonicalJson = (value) =>
  JSON.stringify(value, (_key, v) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, v[k]]))
      : v);

const argsDigest = (args) => createHash('sha256').update(canonicalJson(args), 'utf8').digest('hex');

// trace_id/span_id from the active OpenTelemetry span, if @opentelemetry/api is installed.
async function traceIds() {
  try {
    const { trace } = await import('@opentelemetry/api');
    const ctx = trace.getActiveSpan()?.spanContext();
    if (!ctx || /^0+$/.test(ctx.traceId)) return {};
    return { trace_id: ctx.traceId, span_id: ctx.spanId };
  } catch {
    return {};
  }
}

/**
 * Asks Reede whether `name` may run. Resolves with the response on allow; rejects with
 * ReedeDenied otherwise, including when Reede is unreachable, times out, or answers non-2xx.
 */
export async function check(name, { kind = 'tool', targetHost, args, estCredits, endpoint, headers, timeout = 5 } = {}) {
  const body = { kind, name, ...(await traceIds()) };
  if (targetHost !== undefined) body.target_host = targetHost;
  if (args != null) body.args_digest = argsDigest(args);
  if (estCredits !== undefined) body.est_credits = estCredits;

  const base = (endpoint ?? process.env.REEDE_OTLP_ENDPOINT ?? DEFAULT_ENDPOINT).replace(/\/+$/, '');
  const token = process.env.REEDE_TOKEN;
  const auth = headers ?? (token ? { authorization: `Bearer ${token}` } : {});

  let result;
  try {
    const res = await fetch(`${base}/api/v1/reede/check`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', ...auth },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeout * 1000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    result = await res.json();
  } catch (e) {
    throw new ReedeDenied('deny', `check unavailable: ${e.message}`);
  }
  if (result?.decision === 'allow') return result;
  const decision = result?.decision === 'needs_approval' ? 'needs_approval' : 'deny';
  throw new ReedeDenied(decision, result?.reason, {
    approvalId: result?.approval_id,
    receiptId: result?.receipt_id,
  });
}

/**
 * Wraps a Mastra tool so `execute` asks Reede first. Returns a copy; the original is untouched.
 * Options are those of check(), plus `name` (defaults to the tool's id, then its name).
 */
export function withReedeGuard(tool, { name = tool.id ?? tool.name, ...options } = {}) {
  const execute = tool.execute;
  const guarded = Object.assign(Object.create(Object.getPrototypeOf(tool)), tool);
  guarded.execute = async (input, ...rest) => {
    await check(name, { ...options, args: input });
    return execute.call(tool, input, ...rest);
  };
  return guarded;
}
