// Turns raw Classroom data plus saved state into a flat list of items.
import { classroomDueToDate, parseYmd, startOfDay } from './dates.js';

/** @typedef {{courses: {id:string,name:string}[],
 *   courseWork: {id,courseId,title,description?,alternateLink,dueDate?,dueTime?,creationTime,submissionState?}[],
 *   announcements: {id,courseId,text,alternateLink,creationTime}[],
 *   materials: {id,courseId,title,description?,alternateLink,creationTime}[]}} RawData */
/** @typedef {{id:string, source:'coursework'|'announcement'|'material'|'mine',
 *   courseName:string, title:string, link:string|null, dueAt:Date|null, allDay:boolean,
 *   kind:'homework'|'test'|'activity', done:boolean, needsDate:boolean,
 *   repeatWeekly:boolean, time:string|null, datePicked?:boolean}} Item
 * datePicked: the date came from SavedState.testDates (he picked it), so he can change it. */
/** @typedef {{version:1, checks:Object<string,boolean>, testDates:Object<string,string>,
 *   myItems:{id,kind,title,date,time?,repeatWeekly?}[], updatedAt:number}} SavedState */

const TEST_WORDS = /\b(test|quiz|exam)\b/i;
const DAY_MS = 24 * 60 * 60 * 1000;

/** Classroom says the work is handed in. */
export function isTurnedIn(submissionState) {
  return submissionState === 'TURNED_IN' || submissionState === 'RETURNED';
}

export function isTestText(...strings) {
  return strings.some((s) => typeof s === 'string' && TEST_WORDS.test(s));
}

/**
 * @param {RawData} raw
 * @param {SavedState} saved
 * @param {Date} now
 * @returns {Item[]}
 */
export function buildItems(raw, saved, now) {
  const checks = (saved && saved.checks) || {};
  const testDates = (saved && saved.testDates) || {};
  const myItems = (saved && saved.myItems) || [];
  const cutoff = now.getTime() - 30 * DAY_MS;
  // Unfinished coursework stays longer: Classroom keeps showing it as Missing.
  const openCutoff = now.getTime() - 120 * DAY_MS;
  const courseNames = new Map((raw.courses || []).map((c) => [c.id, c.name]));
  const courseName = (id) => courseNames.get(id) || '';
  const items = [];

  const isDone = (id, submissionState) => (typeof checks[id] === 'boolean'
    ? checks[id]
    : isTurnedIn(submissionState));

  const finish = (item, submissionState) => {
    const override = testDates[item.id];
    if (override) {
      item.dueAt = parseYmd(override);
      item.allDay = true;
    }
    item.datePicked = !!override;
    item.needsDate = item.kind === 'test' && item.dueAt === null;
    item.done = isDone(item.id, submissionState);
    items.push(item);
  };

  for (const w of raw.courseWork || []) {
    const due = classroomDueToDate(w.dueDate, w.dueTime);
    const created = new Date(w.creationTime).getTime();
    const since = isDone(`cw:${w.id}`, w.submissionState) ? cutoff : openCutoff;
    if (due ? due.date.getTime() < since : !(created >= since)) continue;
    finish({
      id: `cw:${w.id}`, source: 'coursework', courseName: courseName(w.courseId),
      title: w.title, link: w.alternateLink || null,
      dueAt: due ? due.date : null, allDay: due ? due.allDay : false,
      kind: isTestText(w.title, w.description) ? 'test' : 'homework',
      done: false, needsDate: false, repeatWeekly: false, time: null,
    }, w.submissionState);
  }

  for (const a of raw.announcements || []) {
    const text = a.text || '';
    if (!isTestText(text) || !(new Date(a.creationTime).getTime() >= cutoff)) continue;
    finish({
      id: `an:${a.id}`, source: 'announcement', courseName: courseName(a.courseId),
      title: (text.split(/\r?\n/).find((l) => l.trim()) || '').trim().slice(0, 80), link: a.alternateLink || null,
      dueAt: null, allDay: false, kind: 'test',
      done: false, needsDate: false, repeatWeekly: false, time: null,
    });
  }

  for (const m of raw.materials || []) {
    if (!isTestText(m.title, m.description) || !(new Date(m.creationTime).getTime() >= cutoff)) continue;
    finish({
      id: `mt:${m.id}`, source: 'material', courseName: courseName(m.courseId),
      title: m.title, link: m.alternateLink || null,
      dueAt: null, allDay: false, kind: 'test',
      done: false, needsDate: false, repeatWeekly: false, time: null,
    });
  }

  for (const m of myItems) {
    const day = startOfDay(parseYmd(m.date));
    let dueAt = day;
    if (m.time) {
      const [h, min] = m.time.split(':').map(Number);
      dueAt = new Date(day.getFullYear(), day.getMonth(), day.getDate(), h, min);
    }
    finish({
      id: `my:${m.id}`, source: 'mine', courseName: '', title: m.title, link: null,
      dueAt, allDay: !m.time, kind: m.kind,
      done: false, needsDate: false, repeatWeekly: !!m.repeatWeekly, time: m.time || null,
    });
  }

  return items;
}
