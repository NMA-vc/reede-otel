import test from 'node:test';
import assert from 'node:assert/strict';
import { reedeOtel } from '../index.js';

test('defaults to local reede serve, no auth', () => {
  delete process.env.REEDE_OTLP_ENDPOINT; delete process.env.REEDE_TOKEN;
  assert.deepEqual(reedeOtel(), { endpoint: 'http://127.0.0.1:4318', headers: {} });
});
test('endpoint and token', () => {
  assert.deepEqual(reedeOtel({ endpoint: 'https://reede.example/', token: 't0k' }),
    { endpoint: 'https://reede.example', headers: { authorization: 'Bearer t0k' } });
});
test('env fallback', () => {
  process.env.REEDE_OTLP_ENDPOINT = 'http://10.0.0.5:4318';
  assert.equal(reedeOtel().endpoint, 'http://10.0.0.5:4318');
  delete process.env.REEDE_OTLP_ENDPOINT;
});
