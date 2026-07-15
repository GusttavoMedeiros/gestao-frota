import assert from 'node:assert/strict';
import test from 'node:test';
import { localISODate } from '../src/lib/date.ts';

test('mantem a data local depois da virada em UTC', () => {
  process.env.TZ = 'America/Sao_Paulo';
  assert.equal(localISODate(new Date('2026-07-15T01:30:00Z')), '2026-07-14');
});
