import test from 'node:test';
import assert from 'node:assert/strict';
import { parseCsv, inspectCsv, caseStatus, sseFrames } from '../frontend/src/core.ts';

// Input fixtures are isolated to tests; the application never loads them.
const headers = 'id,supplier_id,supplier_name,amount,currency,occurred_at,account_fingerprint';
const row = 'test-tx,test-supplier,"Fixture, Inc.",100.00,USD,2026-01-01T00:00:00Z,test-hash';

test('CSV preview preserves quoted commas, escaped quotes, multiline values, BOM and CRLF', () => {
  assert.deepEqual(parseCsv('\uFEFFname,note\r\n"Fixture, Inc.","Line one\nLine ""two"""\r\n'),
    [['name', 'note'], ['Fixture, Inc.', 'Line one\nLine "two"']]);
  assert.equal(inspectCsv(`${headers}\r\n${row}\r\n`).rows[0].supplier_name, 'Fixture, Inc.');
});

test('CSV preview rejects ambiguous quotes and broken record widths', () => {
  assert.throws(() => parseCsv('name\n"unclosed'), /not closed/);
  assert.throws(() => parseCsv('name\n"closed"extra'), /after a closing quote/);
  assert.throws(() => parseCsv('name\npart"quoted'), /must start/);
  assert.throws(() => inspectCsv(`${headers}\n${row},extra`), /Row 2 has 8 values/);
});

test('CSV schema rejects missing, unknown and repeated columns before submission', () => {
  assert.throws(() => inspectCsv(`id,supplier_id\na,b`), /Missing columns/);
  assert.throws(() => inspectCsv(`${headers},unexpected\n${row},value`), /Unrecognized columns/);
  assert.throws(() => inspectCsv(`${headers},id\n${row},other`), /duplicate column names/);
  assert.throws(() => inspectCsv(headers), /between 1 and 1,000/);
});

test('CSV validation identifies duplicate IDs, money precision, currency and timezone errors', () => {
  assert.throws(() => inspectCsv(`${headers}\n${row}\n${row}`), /Row 3: check unique transaction ID/);
  for (const amount of ['0', '-1', '100.001', '1e3']) {
    assert.throws(() => inspectCsv(`${headers}\n${row.replace('100.00', amount)}`), /positive amount/);
  }
  assert.throws(() => inspectCsv(`${headers}\n${row.replace('USD', 'usd')}`), /three-letter currency/);
  assert.throws(() => inspectCsv(`${headers}\n${row.replace('T00:00:00Z', 'T00:00:00')}`), /date with timezone/);
});

test('stream decoder preserves frames split at every byte, including multibyte text', () => {
  const input = ': heartbeat\n\nevent: delta\ndata: {"text":"€ — evidence"}\n\nevent: error\ndata: {"message":"Service interrupted"}\n\n';
  const encoded = new TextEncoder().encode(input);
  const decoder = new TextDecoder();
  let buffer = ''; const frames = [];
  for (const byte of encoded) {
    const result = sseFrames(buffer + decoder.decode(Uint8Array.of(byte), { stream: true }));
    frames.push(...result.frames); buffer = result.remainder;
  }
  assert.equal(buffer, '');
  assert.deepEqual(frames, [
    { event: 'delta', data: { text: '€ — evidence' } },
    { event: 'error', data: { message: 'Service interrupted' } },
  ]);
  assert.equal(sseFrames('event: delta\ndata: {"text":').remainder, 'event: delta\ndata: {"text":');
});

test('case status never presents expired, invalidated or unparseable authorization as ready', () => {
  const now = Date.parse('2026-01-01T00:00:00Z');
  const tx = { id: 'test-tx' };
  const workspace = { decisions: [{ id: tx.id, disposition: 'ready', expires_at: '2026-01-01T00:01:00Z' }], jobs: [] };
  assert.equal(caseStatus(tx, workspace, now), 'ready');
  assert.equal(caseStatus(tx, workspace, now + 60000), 'stale');
  workspace.decisions[0].invalidated_at = '2025-12-31T23:59:00Z';
  assert.equal(caseStatus(tx, workspace, now), 'stale');
  delete workspace.decisions[0].invalidated_at;
  workspace.decisions[0].expires_at = 'invalid';
  assert.equal(caseStatus(tx, workspace, now), 'stale');
  workspace.decisions = [];
  workspace.jobs = [{ target: tx.id, kind: 'investigate', status: 'failed' }];
  assert.equal(caseStatus(tx, workspace, now), 'failed');
  workspace.jobs[0].status = 'running';
  assert.equal(caseStatus(tx, workspace, now), 'running');
  assert.equal(caseStatus(tx, null, now), 'queued');
});

test('seeded transactions without an actual assessment job are not shown as running', () => {
  assert.equal(caseStatus({ id: 'syn-v1-0000000001', synthetic: true }, { decisions: [], jobs: [] }), 'not_assessed');
});
