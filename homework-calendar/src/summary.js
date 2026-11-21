// What's next, checklist and week grid, built from Items.
import { startOfDay, addDays, sameDay } from './dates.js';

const byTitle = (a, b) => a.title.localeCompare(b.title);
const byDue = (a, b) => a.dueAt - b.dueAt || byTitle(a, b);

export function isOverdue(item, now) {
  if (item.done || item.kind === 'activity' || !item.dueAt) return false;
  if (item.allDay) return startOfDay(item.dueAt) < startOfDay(now);
  return item.dueAt < now;
}

export function whatsNext(items, now) {
  const today = startOfDay(now);
  const tomorrow = addDays(today, 1);
  const weekEnd = addDays(today, 7); // exclusive: today .. today+6
  const open = items.filter((i) => !i.done);

  const tests = open
    .filter((i) => i.kind === 'test' && i.dueAt && startOfDay(i.dueAt) >= today && startOfDay(i.dueAt) < weekEnd)
    .sort(byDue);
  const needsDate = open.filter((i) => i.needsDate).sort(byTitle);
  // Overdue: any missed homework or test (a timed test earlier today stays under tests).
  const overdue = open.filter((i) => isOverdue(i, now) && !tests.includes(i)).sort(byDue);
  const homework = open.filter((i) => i.kind === 'homework' && i.dueAt);
  const notLate = homework.filter((i) => !isOverdue(i, now));
  return {
    tests,
    needsDate,
    overdue,
    today: notLate.filter((i) => sameDay(i.dueAt, today)).sort(byDue),
    tomorrow: notLate.filter((i) => sameDay(i.dueAt, tomorrow)).sort(byDue),
  };
}

export function checklist(items, now) {
  const own = items.filter((i) => i.kind !== 'activity');
  const cutoff = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const wrap = (status) => (item) => ({ item, status });
  const overdue = own.filter((i) => isOverdue(i, now)).sort(byDue).map(wrap('overdue'));
  const openDated = own.filter((i) => !i.done && i.dueAt && !isOverdue(i, now)).sort(byDue).map(wrap('open'));
  const openUndated = own.filter((i) => !i.done && !i.dueAt).sort(byTitle).map(wrap('open'));
  const done = own.filter((i) => i.done && i.dueAt && i.dueAt >= cutoff).sort(byDue).map(wrap('done'));
  return [...overdue, ...openDated, ...openUndated, ...done];
}

const minutes = (d) => d.getHours() * 60 + d.getMinutes();

function inDayOrder(a, b) {
  if (a.allDay !== b.allDay) return a.allDay ? 1 : -1;
  if (!a.allDay) return minutes(a.dueAt) - minutes(b.dueAt) || byTitle(a, b);
  return byTitle(a, b);
}

export function weekDays(items, weekStart) {
  const dated = items.filter((i) => i.dueAt);
  return Array.from({ length: 7 }, (_, n) => {
    const date = addDays(weekStart, n);
    const here = dated.filter((i) => {
      if (sameDay(i.dueAt, date)) return true;
      return i.repeatWeekly && startOfDay(i.dueAt) < date && i.dueAt.getDay() === date.getDay();
    });
    return { date, items: here.sort(inDayOrder) };
  });
}
