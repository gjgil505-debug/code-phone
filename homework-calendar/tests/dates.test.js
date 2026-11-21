import test from 'node:test';
import assert from 'node:assert/strict';
import { classroomDueToDate, ymd, parseYmd, startOfWeek, addDays } from '../src/dates.js';

test('UTC due time maps to the local day', () => {
  // 11:59pm Pacific on Nov 24 is stored as Nov 25 07:59 UTC
  const r = classroomDueToDate({year:2026,month:11,day:25},{hours:7,minutes:59});
  assert.equal(ymd(r.date), '2026-11-24'); assert.equal(r.allDay, false);
});
test('missing dueTime is all-day on that date', () => {
  const r = classroomDueToDate({year:2026,month:11,day:25}, undefined);
  assert.equal(ymd(r.date), '2026-11-25'); assert.equal(r.allDay, true);
});
test('no dueDate returns null', () => assert.equal(classroomDueToDate(undefined, undefined), null));
test('startOfWeek is Monday', () => {
  assert.equal(ymd(startOfWeek(parseYmd('2026-11-29'))), '2026-11-23'); // Sunday -> Monday before
  assert.equal(ymd(startOfWeek(parseYmd('2026-11-23'))), '2026-11-23');
});
test('addDays crosses month end', () => assert.equal(ymd(addDays(parseYmd('2026-11-30'), 1)), '2026-12-01'));
test('empty dueTime is midnight UTC, not all-day', () => {
  const r = classroomDueToDate({year:2026,month:11,day:25}, {});
  assert.equal(r.allDay, false);
  assert.equal(r.date.toISOString(), '2026-11-25T00:00:00.000Z');
});
