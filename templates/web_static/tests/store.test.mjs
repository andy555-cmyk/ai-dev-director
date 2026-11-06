import { test } from 'node:test';
import assert from 'node:assert/strict';
import { load, save, exportJson, importJson, memoryStorage, emptyData } from '../app/store.js';

test('empty storage gives empty data', () => { assert.deepEqual(load(memoryStorage()), emptyData()); });
test('save then load round-trips', () => { const s = memoryStorage(); save({ version: 1, x: [1] }, s); assert.deepEqual(load(s), { version: 1, x: [1] }); });
test('invalid restore keeps current data', () => {
  const s = memoryStorage(); save({ version: 1, keep: true }, s);
  assert.throws(() => importJson('{"version":2}', s)); assert.throws(() => importJson('not json', s));
  assert.deepEqual(load(s), { version: 1, keep: true });
  importJson(exportJson({ version: 1, ok: 1 }), s); assert.equal(load(s).ok, 1);
});
