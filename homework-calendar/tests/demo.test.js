import test from 'node:test';
import assert from 'node:assert/strict';
import { demoData } from '../src/demo.js';
import { buildItems } from '../src/items.js';
import { whatsNext } from '../src/summary.js';
import { normalizeState } from '../src/store.js';

test('demoData runs through buildItems/whatsNext with something in every group, any weekday', () => {
  for (let d = 0; d < 14; d++) {
    for (const h of [0, 8, 15, 23]) {
      const now = new Date(2026, 10, 16 + d, h, 30);
      const { raw, saved } = demoData(now);
      assert.deepEqual(normalizeState(saved), saved);
      const items = buildItems(raw, saved, now);
      const s = whatsNext(items, now);
      for (const k of ['tests', 'needsDate', 'overdue', 'today', 'tomorrow']) {
        assert.ok(s[k].length > 0, `${k} empty at ${now}`);
      }
      assert.ok(items.some((i) => i.done && i.source === 'coursework'));
      assert.ok(s.overdue.some((i) => i.kind === 'test'), `no overdue test at ${now}`);
      assert.ok(items.some((i) => i.title === 'Soccer' && i.repeatWeekly && i.time === '17:00'));
      assert.ok(items.some((i) => i.title.includes('<') && i.title.includes('&')));
      assert.equal(raw.courses.length, 3);
    }
  }
});
