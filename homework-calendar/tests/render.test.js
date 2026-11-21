import test from 'node:test';
import assert from 'node:assert/strict';
import { escapeHtml, renderWhatsNext, renderWeek, renderChecklist } from '../src/render.js';

const now = new Date(2026, 10, 23, 15, 0); // Mon Nov 23 2026
const item = (o = {}) => ({
  id: 'cw:1', source: 'coursework', courseName: 'Math', title: 'T', link: null,
  dueAt: new Date(2026, 10, 24), allDay: true, kind: 'homework', done: false,
  needsDate: false, repeatWeekly: false, time: null, ...o,
});
const empty = { tests: [], needsDate: [], overdue: [], today: [], tomorrow: [] };

test('escapeHtml', () => assert.equal(escapeHtml(`<a href="x">&'`), '&lt;a href=&quot;x&quot;&gt;&amp;&#39;'));

test('Classroom titles are escaped in every renderer', () => {
  const bad = item({ title: 'Quiz: <b> & <i>', courseName: '<u>', link: 'x" onclick="y', id: 'cw:"1' });
  const outs = [
    renderWhatsNext({ ...empty, overdue: [bad], tests: [{ ...bad, kind: 'test' }], needsDate: [bad] }, now),
    renderWeek([{ date: new Date(2026, 10, 24), items: [bad] }], now),
    renderChecklist([{ item: bad, status: 'open' }], now),
  ];
  for (const o of outs) {
    assert.ok(o.includes('Quiz: &lt;b&gt; &amp; &lt;i&gt;'));
    assert.ok(!o.includes('<b>') && !o.includes('<u>') && !o.includes('onclick="y'));
  }
});

test('overdue and done classes, today class, times, links', () => {
  const days = [
    { date: new Date(2026, 10, 22), items: [item({ dueAt: new Date(2026, 10, 22) })] },
    { date: new Date(2026, 10, 23), items: [
      item({ id: 'my:s', source: 'mine', kind: 'activity', title: 'Soccer', dueAt: new Date(2026, 10, 23, 17), allDay: false }),
      item({ id: 'cw:2', kind: 'test', done: true, link: 'https://x/y' }),
      item({ id: 'my:m', source: 'mine', kind: 'activity', title: 'Band', dueAt: new Date(2026, 10, 23, 9, 30), allDay: false }),
    ] },
  ];
  const out = renderWeek(days, now);
  assert.match(out, /item kind-homework overdue/);
  assert.match(out, /class="day today"/);
  assert.match(out, /5:00pm/);
  assert.match(out, /9:30am/);
  assert.match(out, /kind-test done/);
  assert.match(out, /TEST/);
  assert.match(out, /href="https:\/\/x\/y" target="_blank" rel="noopener"/);
  assert.match(out, /data-action="edit" data-id="my:s"/);
});

test('needs-date line has set-date button', () => {
  const out = renderWhatsNext({ ...empty, needsDate: [item({ id: 'an:9', kind: 'test', courseName: 'English', dueAt: null, needsDate: true })] }, now);
  assert.match(out, /Test mentioned in English: add a date/);
  assert.match(out, /data-action="set-date" data-id="an:9"/);
});

test('test lines', () => {
  const t = (d) => item({ kind: 'test', title: 'Quiz', dueAt: d });
  const out = renderWhatsNext({ ...empty, tests: [t(new Date(2026, 10, 23)), t(new Date(2026, 10, 24)), t(new Date(2026, 10, 27))] }, now);
  assert.match(out, /⚠ TEST today: Quiz/);
  assert.match(out, /⚠ TEST tomorrow: Quiz/);
  assert.match(out, /⚠ TEST Friday: Quiz/);
});

test('empty summary says Nothing due. Nice!', () => {
  assert.match(renderWhatsNext(empty, now), /Nothing due\. Nice!/);
  assert.ok(!renderWhatsNext(empty, now).includes('<section'));
});

test('checklist rows and due labels', () => {
  const rows = [
    { item: item({ id: 'a', dueAt: new Date(2026, 10, 23) }), status: 'open' },
    { item: item({ id: 'b', dueAt: new Date(2026, 10, 24) }), status: 'open' },
    { item: item({ id: 'c', dueAt: new Date(2026, 10, 27) }), status: 'open' },
    { item: item({ id: 'd', dueAt: new Date(2026, 10, 30) }), status: 'open' },
    { item: item({ id: 'e', dueAt: null }), status: 'open' },
    { item: item({ id: 'f', done: true }), status: 'done' },
  ];
  const out = renderChecklist(rows, now);
  for (const l of ['today', 'tomorrow', 'Friday', 'Nov 30', 'no date']) assert.ok(out.includes(`>${l}<`), l);
  assert.match(out, /<label class="row done"><input type="checkbox" data-action="check" data-id="f" checked>/);
  assert.match(out, /<input type="checkbox" data-action="check" data-id="a">/);
});
