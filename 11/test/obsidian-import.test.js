import test from 'node:test';
import assert from 'node:assert/strict';
import {parseDone} from '../scripts/import-obsidian.js';

test('Obsidian: formatos, enlaces múltiples, empresa desconocida y fecha histórica', () => {
  const rows = parseDone(`- 2026-11-11: inscripción — Backend | Empresa | ats:123 — hecho @url:https://example.org/jobs/123?utm_source=note @url:https://example.org/123
- 2026-11-10: desestimada — Software — InfoJobs | infojobs:sin-ID — hecho`);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows[0].urls, ['https://example.org/jobs/123','https://example.org/123']);
  assert.equal(rows[0].input.application_state, 'enviada');
  assert.equal(rows[0].input.submitted_at, null);
  assert.equal(rows[1].input.company, 'Empresa no indicada');
  assert.equal(rows[1].input.review_state, 'descartada');
  assert.equal(rows[1].externalId, null);
  assert.equal(parseDone(rows[0].raw)[0].key, rows[0].key);
  assert.throws(() => parseDone('- 2026-02-30: inscripción — Backend | Empresa | ats:123 — hecho'));
  assert.throws(() => parseDone('- 2026-11-11: rechazada — Backend | Empresa | ats:123 — hecho'));
});
