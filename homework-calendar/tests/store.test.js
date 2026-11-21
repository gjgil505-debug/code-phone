import test from 'node:test';
import assert from 'node:assert/strict';
import {
  emptyState, normalizeState, setCheck, setTestDate,
  addMyItem, updateMyItem, deleteMyItem, pickNewer,
} from '../src/store.js';

test('normalizeState handles null, "", "{bad", [], and {checks: 5}', () => {
  for (const x of [null, '', '{bad', [], {checks: 5}, 7, undefined]) assert.deepEqual(normalizeState(x), emptyState());
});

test('normalizeState accepts a JSON string and keeps good fields', () => {
  const raw = JSON.stringify({version: 9, checks: {a: true, b: 'x', c: false}, testDates: {a: '2026-11-24', b: 'nope', c: '2026-02-31'}, myItems: [], updatedAt: 5});
  assert.deepEqual(normalizeState(raw), {version: 1, checks: {a: true, c: false}, testDates: {a: '2026-11-24'}, myItems: [], updatedAt: 5});
  assert.equal(normalizeState({updatedAt: 'x'}).updatedAt, 0);
  assert.equal(normalizeState({updatedAt: Infinity}).updatedAt, 0);
});

test('normalizeState drops broken myItems and keeps good ones', () => {
  const s = normalizeState({myItems: [
    {id: '1', kind: 'activity', title: 'Soccer', date: '2026-11-24', time: '16:30', repeatWeekly: true},
    {id: '2', kind: 'test', title: 'Math', date: '2026-11-25', time: 'late'},
    {id: '', kind: 'test', title: 'x', date: '2026-11-25'},
    {id: '3', kind: 'test', title: '', date: '2026-11-25'},
    {id: '4', kind: 'test', title: 'x', date: '2026-13-01'},
    {id: '5', kind: 'bogus', title: 'x', date: '2026-11-25'},
    null, 'str',
  ]});
  assert.deepEqual(s.myItems, [
    {id: '1', kind: 'activity', title: 'Soccer', date: '2026-11-24', time: '16:30', repeatWeekly: true},
    {id: '2', kind: 'test', title: 'Math', date: '2026-11-25'},
  ]);
});

test('setCheck does not mutate and bumps updatedAt', () => {
  const a = emptyState();
  const b = setCheck(a, 'cw:1', true, 100);
  assert.deepEqual(a, emptyState());
  assert.deepEqual(b.checks, {'cw:1': true});
  assert.equal(b.updatedAt, 100);
});

test('setTestDate sets a date', () => {
  const b = setTestDate(emptyState(), 'cw:1', '2026-12-01', 50);
  assert.deepEqual(b.testDates, {'cw:1': '2026-12-01'});
  assert.equal(b.updatedAt, 50);
});

test('addMyItem trims title and uses makeId', () => {
  const s = addMyItem(emptyState(), {kind: 'activity', title: '  Soccer ', date: '2026-11-24', time: '16:00', repeatWeekly: true}, 7, () => 'abc');
  assert.deepEqual(s.myItems, [{id: 'abc', kind: 'activity', title: 'Soccer', date: '2026-11-24', time: '16:00', repeatWeekly: true}]);
  assert.equal(s.updatedAt, 7);
  assert.throws(() => addMyItem(emptyState(), {kind: 'test', title: '   ', date: '2026-11-24'}, 1), /Name is required/);
});

test('updateMyItem edits, trims, and ignores unknown ids', () => {
  const s = addMyItem(emptyState(), {kind: 'test', title: 'A', date: '2026-11-24'}, 1, () => 'x');
  const u = updateMyItem(s, 'x', {title: ' B ', date: '2026-11-30'}, 2);
  assert.equal(u.myItems[0].title, 'B');
  assert.equal(u.myItems[0].date, '2026-11-30');
  assert.equal(u.updatedAt, 2);
  assert.equal(s.myItems[0].title, 'A');
  assert.throws(() => updateMyItem(s, 'x', {title: ' '}, 3), /Name is required/);
  assert.equal(updateMyItem(s, 'nope', {title: 'Z'}, 3), s);
});

test('deleteMyItem removes its check', () => {
  let s = addMyItem(emptyState(), {kind: 'test', title: 'A', date: '2026-11-24'}, 1, () => 'x');
  s = setCheck(s, 'my:x', true, 2);
  s = setCheck(s, 'cw:1', true, 3);
  const d = deleteMyItem(s, 'x', 4);
  assert.deepEqual(d.myItems, []);
  assert.deepEqual(d.checks, {'cw:1': true});
  assert.equal(d.updatedAt, 4);
});

test('pickNewer prefers later updatedAt', () => {
  const a = {...emptyState(), updatedAt: 1}, b = {...emptyState(), updatedAt: 2}, c = {...emptyState(), updatedAt: 1};
  assert.equal(pickNewer(a, b), b);
  assert.equal(pickNewer(b, a), b);
  assert.equal(pickNewer(a, c), a);
});
