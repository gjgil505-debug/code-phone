import test from 'node:test';
import assert from 'node:assert/strict';
import { isTestText, buildItems } from '../src/items.js';
import { ymd } from '../src/dates.js';

const now = new Date(2026, 10, 23, 15, 0);
const iso = (d) => d.toISOString();
const raw = (over = {}) => ({
  courses: [{ id: 'c1', name: 'Math' }],
  courseWork: [], announcements: [], materials: [], ...over,
});
const saved = (over = {}) => ({ version: 1, checks: {}, testDates: {}, myItems: [], updatedAt: 0, ...over });
const find = (items, id) => items.find((i) => i.id === id);

test('test words match whole words only', () => {
  assert.ok(isTestText('Unit 4 Quiz')); assert.ok(isTestText('', 'TEST on friday'));
  assert.ok(isTestText('Final Exam')); assert.ok(!isTestText('Science contest'));
  assert.ok(!isTestText('Testing the volcano'));
});

test('coursework due date, kind, and turned-in auto-tick', () => {
  const items = buildItems(raw({ courseWork: [
    { id: 'a', courseId: 'c1', title: 'Worksheet', alternateLink: 'http://a', dueDate: { year: 2026, month: 11, day: 25 }, creationTime: iso(now), submissionState: 'TURNED_IN' },
    { id: 'b', courseId: 'c1', title: 'Quiz 3', alternateLink: 'http://b', dueDate: { year: 2026, month: 11, day: 26 }, creationTime: iso(now), submissionState: 'CREATED' },
  ] }), saved(), now);
  const a = find(items, 'cw:a'), b = find(items, 'cw:b');
  assert.equal(a.kind, 'homework'); assert.equal(a.done, true);
  assert.equal(a.allDay, true); assert.equal(ymd(a.dueAt), '2026-11-25');
  assert.equal(a.courseName, 'Math'); assert.equal(a.link, 'http://a');
  assert.equal(a.source, 'coursework'); assert.equal(a.time, null);
  assert.equal(b.kind, 'test'); assert.equal(b.done, false); assert.equal(b.needsDate, false);
});

test('manual check overrides submission state', () => {
  const items = buildItems(raw({ courseWork: [
    { id: 'a', courseId: 'c1', title: 'Worksheet', alternateLink: 'x', dueDate: { year: 2026, month: 11, day: 25 }, creationTime: iso(now), submissionState: 'TURNED_IN' },
  ] }), saved({ checks: { 'cw:a': false } }), now);
  assert.equal(find(items, 'cw:a').done, false);
});

test('announcement without test words is dropped; with them needsDate', () => {
  const items = buildItems(raw({ announcements: [
    { id: 'a1', courseId: 'c1', text: 'Test on Friday!\nBring a pencil', alternateLink: 'l', creationTime: iso(now) },
    { id: 'a2', courseId: 'c1', text: 'Field trip Friday', alternateLink: 'l', creationTime: iso(now) },
  ] }), saved(), now);
  assert.equal(find(items, 'an:a2'), undefined);
  const t = find(items, 'an:a1');
  assert.equal(t.kind, 'test'); assert.equal(t.needsDate, true);
  assert.equal(t.dueAt, null); assert.equal(t.title, 'Test on Friday!');
});

test('testDates gives an undated test a date', () => {
  const items = buildItems(raw({ announcements: [
    { id: 'a1', courseId: 'c1', text: 'Test on Friday!', alternateLink: 'l', creationTime: iso(now) },
  ] }), saved({ testDates: { 'an:a1': '2026-11-27' } }), now);
  const t = find(items, 'an:a1');
  assert.equal(ymd(t.dueAt), '2026-11-27'); assert.equal(t.allDay, true); assert.equal(t.needsDate, false);
});

test('old coursework is dropped', () => {
  const items = buildItems(raw({ courseWork: [
    { id: 'o', courseId: 'c1', title: 'Old', alternateLink: 'x', dueDate: { year: 2026, month: 10, day: 9 }, creationTime: iso(new Date(2026, 8, 1)) },
  ] }), saved(), now);
  assert.equal(find(items, 'cw:o'), undefined);
});

test('my items become items', () => {
  const s = saved({ myItems: [{ id: 'x', kind: 'activity', title: 'Soccer', date: '2026-11-24', time: '17:00', repeatWeekly: true }] });
  const [it] = buildItems(raw(), s, now);
  assert.equal(it.id, 'my:x'); assert.equal(it.source, 'mine'); assert.equal(it.allDay, false);
  assert.equal(it.dueAt.getTime(), new Date(2026, 10, 24, 17, 0).getTime());
  assert.equal(it.repeatWeekly, true); assert.equal(it.time, '17:00');
  assert.equal(it.link, null); assert.equal(it.courseName, '');
});
