// Made-up sample data for trying the app without Google. All dates relative to `now`.
import { startOfDay, addDays, startOfWeek, ymd } from './dates.js';
import { emptyState } from './store.js';

export function demoData(now) {
  const today = startOfDay(now);
  const allDay = (d) => ({ year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate() });
  // Timed Classroom dues are UTC: use the UTC fields of the local target moment.
  const timed = (d, h) => {
    const t = new Date(d.getFullYear(), d.getMonth(), d.getDate(), h, 0);
    return {
      dueDate: { year: t.getUTCFullYear(), month: t.getUTCMonth() + 1, day: t.getUTCDate() },
      dueTime: { hours: t.getUTCHours(), minutes: t.getUTCMinutes() },
    };
  };
  const created = new Date(now.getTime() - 2 * 86400000).toISOString();
  const link = (id) => `https://classroom.google.com/c/demo/a/${id}`;
  const cw = (id, courseId, title, due, submissionState = 'CREATED') =>
    ({ id, courseId, title, alternateLink: link(id), creationTime: created, submissionState, ...due });

  const raw = {
    courses: [
      { id: 'c1', name: 'Math' },
      { id: 'c2', name: 'Science' },
      { id: 'c3', name: 'English' },
    ],
    courseWork: [
      cw('w1', 'c1', 'Worksheet 4.2', { dueDate: allDay(addDays(today, -2)) }),
      cw('w2', 'c2', 'Lab report', { dueDate: allDay(today) }),
      cw('w3', 'c3', 'Read chapter 5', timed(addDays(today, 1), 15)),
      cw('w4', 'c1', 'Fractions: 1/2 < 3/4 & more', { dueDate: allDay(addDays(today, 1)) }),
      cw('w5', 'c3', 'Book report', { dueDate: allDay(addDays(today, -1)) }, 'TURNED_IN'),
      cw('w6', 'c2', 'Unit 4 Quiz', { dueDate: allDay(addDays(today, 2)) }),
    ],
    announcements: [
      { id: 'a1', courseId: 'c3', text: 'Test on Friday!', alternateLink: link('a1'), creationTime: created },
    ],
    materials: [],
  };

  const saved = emptyState();
  saved.myItems.push({
    id: 'soccer', kind: 'activity', title: 'Soccer',
    date: ymd(addDays(startOfWeek(now), 2)), time: '17:00', repeatWeekly: true,
  });
  return { raw, saved };
}
