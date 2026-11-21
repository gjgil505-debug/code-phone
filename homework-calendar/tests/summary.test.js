import test from 'node:test';
import assert from 'node:assert/strict';
import { isOverdue, whatsNext, checklist, weekDays } from '../src/summary.js';
import { parseYmd } from '../src/dates.js';

const now = new Date(2026, 10, 23, 15, 0); // Mon Nov 23 2026, 3pm local

function item(o = {}) {
  return {
    id: 'x', source: 'coursework', courseName: 'Math', title: 'T', link: null,
    dueAt: null, allDay: true, kind: 'homework', done: false, needsDate: false,
    repeatWeekly: false, time: null, ...o,
  };
}
const day = (m, d) => new Date(2026, m - 1, d);
const at = (m, d, h, min = 0) => new Date(2026, m - 1, d, h, min);
const ids = (arr) => arr.map((x) => (x.item ? x.item.id : x.id));

test('timed homework earlier today is overdue; all-day today is not', () => {
  assert.equal(isOverdue(item({ dueAt: at(11, 23, 9), allDay: false }), now), true);
  assert.equal(isOverdue(item({ dueAt: at(11, 23, 18), allDay: false }), now), false);
  assert.equal(isOverdue(item({ dueAt: day(11, 23) }), now), false);
  assert.equal(isOverdue(item({ dueAt: day(11, 22) }), now), true);
  assert.equal(isOverdue(item({ dueAt: day(11, 22), done: true }), now), false);
  assert.equal(isOverdue(item({ dueAt: day(11, 22), kind: 'activity' }), now), false);
  assert.equal(isOverdue(item({ dueAt: null }), now), false);
});

test('whatsNext groups tests this week, overdue, today, tomorrow; skips activities and done', () => {
  const items = [
    item({ id: 'late', dueAt: day(11, 20) }),
    item({ id: 'missed-quiz', kind: 'test', title: 'Chapter 3 Quiz', dueAt: day(11, 21) }),
    item({ id: 'missed-quiz-done', kind: 'test', dueAt: day(11, 21), done: true }),
    item({ id: 'old-soccer', kind: 'activity', dueAt: day(11, 21) }),
    item({ id: 'earlier-today', dueAt: at(11, 23, 9), allDay: false }),
    item({ id: 'today-allday', dueAt: day(11, 23) }),
    item({ id: 'today-evening', dueAt: at(11, 23, 18), allDay: false }),
    item({ id: 'tomorrow', dueAt: day(11, 24) }),
    item({ id: 'done-today', dueAt: day(11, 23), done: true }),
    item({ id: 'soccer', kind: 'activity', dueAt: day(11, 23) }),
    item({ id: 'test-b', kind: 'test', dueAt: day(11, 27), title: 'B' }),
    item({ id: 'test-a', kind: 'test', dueAt: day(11, 25), title: 'A' }),
    item({ id: 'test-today-early', kind: 'test', dueAt: at(11, 23, 9), allDay: false }),
    item({ id: 'test-done', kind: 'test', dueAt: day(11, 24), done: true }),
    item({ id: 'nodate', needsDate: true, kind: 'test' }),
    item({ id: 'nodate-done', needsDate: true, done: true }),
  ];
  const r = whatsNext(items, now);
  assert.deepEqual(ids(r.tests), ['test-today-early', 'test-a', 'test-b']);
  assert.deepEqual(ids(r.needsDate), ['nodate']);
  assert.deepEqual(ids(r.overdue), ['late', 'missed-quiz', 'earlier-today']);
  assert.deepEqual(ids(r.today), ['today-allday', 'today-evening']);
  assert.deepEqual(ids(r.tomorrow), ['tomorrow']);
});

test('test 8 days out is not in tests this week', () => {
  const items = [
    item({ id: 'in6', kind: 'test', dueAt: day(11, 29) }),
    item({ id: 'in7', kind: 'test', dueAt: day(11, 30) }),
    item({ id: 'in8', kind: 'test', dueAt: day(12, 1) }),
  ];
  assert.deepEqual(ids(whatsNext(items, now).tests), ['in6']);
});

test('checklist order: overdue, open dated, open undated, done recent', () => {
  const items = [
    item({ id: 'done-soon', dueAt: day(11, 25), done: true }),
    item({ id: 'undated', needsDate: true }),
    item({ id: 'open-later', dueAt: day(11, 27) }),
    item({ id: 'overdue-new', dueAt: day(11, 22) }),
    item({ id: 'done-recent', dueAt: day(11, 20), done: true }),
    item({ id: 'open-soon', dueAt: day(11, 24) }),
    item({ id: 'overdue-old', dueAt: day(11, 18) }),
    item({ id: 'act', kind: 'activity', dueAt: day(11, 24) }),
  ];
  const r = checklist(items, now);
  assert.deepEqual(ids(r), ['overdue-old', 'overdue-new', 'open-soon', 'open-later', 'undated', 'done-recent', 'done-soon']);
  assert.deepEqual(r.map((x) => x.status), ['overdue', 'overdue', 'open', 'open', 'open', 'done', 'done']);
});

test('done item from 10 days ago is left out of the checklist', () => {
  const items = [
    item({ id: 'old', dueAt: day(11, 13), done: true }),
    item({ id: 'nodate-done', done: true }),
  ];
  assert.deepEqual(ids(checklist(items, now)), []);
});

test('weekly activity repeats on its weekday, not before its start date', () => {
  const soccer = item({ id: 'soccer', kind: 'activity', dueAt: day(11, 25), repeatWeekly: true });
  const w1 = weekDays([soccer], parseYmd('2026-11-23'));
  assert.equal(w1.length, 7);
  assert.deepEqual(w1.map((d) => ids(d.items)), [[], [], ['soccer'], [], [], [], []]);
  const w2 = weekDays([soccer], parseYmd('2026-11-30'));
  assert.deepEqual(w2.map((d) => ids(d.items)), [[], [], ['soccer'], [], [], [], []]);
  assert.equal(w2[2].date.getDate(), 2);
  const wBefore = weekDays([soccer], parseYmd('2026-11-16'));
  assert.deepEqual(wBefore.map((d) => ids(d.items)), [[], [], [], [], [], [], []]);
});

test('weekDays sorts timed before all-day', () => {
  const items = [
    item({ id: 'allday', dueAt: day(11, 24), title: 'A' }),
    item({ id: 'late', dueAt: at(11, 24, 16), allDay: false }),
    item({ id: 'early', dueAt: at(11, 24, 8), allDay: false }),
    item({ id: 'other-week', dueAt: day(12, 1) }),
    item({ id: 'nodate' }),
  ];
  const w = weekDays(items, parseYmd('2026-11-23'));
  assert.deepEqual(ids(w[1].items), ['early', 'late', 'allday']);
  assert.deepEqual(w.flatMap((d) => ids(d.items)).length, 3);
});

test('an overdue undone test is in overdue, so What\'s next is never empty while it is missed', () => {
  const r = whatsNext([item({ id: 'quiz', kind: 'test', title: 'Chapter 3 Quiz', dueAt: day(11, 20) })], now);
  assert.deepEqual(ids(r.overdue), ['quiz']);
  assert.deepEqual(ids(r.tests), []);
  // A timed test earlier today stays under tests (TEST today), not twice.
  const t = whatsNext([item({ id: 'early', kind: 'test', dueAt: at(11, 23, 9), allDay: false })], now);
  assert.deepEqual(ids(t.tests), ['early']);
  assert.deepEqual(ids(t.overdue), []);
});
