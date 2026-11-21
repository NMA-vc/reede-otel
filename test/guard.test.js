import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { check, withReedeGuard, ReedeDenied } from '../index.js';

// A local stand-in for `reede serve`: answers POST /api/v1/reede/check with a fixed reply.
async function stub(status, body) {
  const seen = [];
  const server = createServer((req, res) => {
    let raw = '';
    req.on('data', (c) => { raw += c; });
    req.on('end', () => {
      seen.push({ path: req.url, headers: req.headers, body: JSON.parse(raw) });
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify(body));
    });
  });
  await new Promise((ok) => server.listen(0, '127.0.0.1', ok));
  return { seen, endpoint: `http://127.0.0.1:${server.address().port}`, close: () => new Promise((ok) => server.close(ok)) };
}

// A base URL with nothing listening: the connection is refused.
async function deadEndpoint() {
  const server = createServer();
  await new Promise((ok) => server.listen(0, '127.0.0.1', ok));
  const endpoint = `http://127.0.0.1:${server.address().port}`;
  await new Promise((ok) => server.close(ok));
  return endpoint;
}

// Mastra-shaped tool: an id, a description and an execute(input, context) that counts its runs.
function makeTool(counter) {
  return {
    id: 'lookup',
    description: 'Look up a fact',
    execute: async (input) => { counter.ran += 1; return `fact about ${input.topic}`; },
  };
}

test('allow runs the tool', async () => {
  delete process.env.REEDE_TOKEN;
  const s = await stub(200, { decision: 'allow', receipt_id: 'r1' });
  try {
    const counter = { ran: 0 };
    const guarded = withReedeGuard(makeTool(counter), { endpoint: s.endpoint });
    assert.equal(await guarded.execute({ topic: 'receipts' }), 'fact about receipts');
    assert.equal(counter.ran, 1);
    assert.equal(s.seen[0].path, '/api/v1/reede/check');
    assert.equal(s.seen[0].body.kind, 'tool');
    assert.equal(s.seen[0].body.name, 'lookup');
    assert.equal(s.seen[0].body.args_digest.length, 64);
  } finally { await s.close(); }
});

test('deny raises and does not run the tool', async () => {
  const s = await stub(200, { decision: 'deny', reason: 'not on the allowlist', receipt_id: 'r2' });
  try {
    const counter = { ran: 0 };
    const guarded = withReedeGuard(makeTool(counter), { endpoint: s.endpoint });
    await assert.rejects(guarded.execute({ topic: 'x' }), (err) =>
      err instanceof ReedeDenied && err.decision === 'deny' &&
      err.reason === 'not on the allowlist' && err.receiptId === 'r2');
    assert.equal(counter.ran, 0);
  } finally { await s.close(); }
});

test('needs_approval raises with approvalId', async () => {
  const s = await stub(200, { decision: 'needs_approval', reason: 'over threshold', approval_id: 'ap-7', receipt_id: 'r3' });
  try {
    await assert.rejects(check('transfer', { endpoint: s.endpoint }), (err) =>
      err instanceof ReedeDenied && err.decision === 'needs_approval' && err.approvalId === 'ap-7');
  } finally { await s.close(); }
});

test('server down fails closed and does not run the tool', async () => {
  const counter = { ran: 0 };
  const guarded = withReedeGuard(makeTool(counter), { endpoint: await deadEndpoint(), timeout: 2 });
  await assert.rejects(guarded.execute({ topic: 'x' }), (err) =>
    err instanceof ReedeDenied && err.decision === 'deny' && err.reason.startsWith('check unavailable'));
  assert.equal(counter.ran, 0);
});

test('non-2xx fails closed', async () => {
  const s = await stub(500, { decision: 'allow' });
  try {
    await assert.rejects(check('lookup', { endpoint: s.endpoint }), (err) =>
      err instanceof ReedeDenied && err.reason.startsWith('check unavailable'));
  } finally { await s.close(); }
});

test('args digest is stable regardless of key order', async () => {
  const s = await stub(200, { decision: 'allow' });
  try {
    await check('t', { endpoint: s.endpoint, args: { b: 1, a: { y: 2, x: [1, 2] } } });
    await check('t', { endpoint: s.endpoint, args: { a: { x: [1, 2], y: 2 }, b: 1 } });
    assert.equal(s.seen[0].body.args_digest, s.seen[1].body.args_digest);
    // Fixed vector, shared with the Python test: sha256 of the canonical JSON '{"a":2,"b":1}'.
    await check('t', { endpoint: s.endpoint, args: { b: 1, a: 2 } });
    assert.equal(s.seen[2].body.args_digest, createHash('sha256').update('{"a":2,"b":1}').digest('hex'));
  } finally { await s.close(); }
});
