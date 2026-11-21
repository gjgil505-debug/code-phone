// Date helpers. All results are in the runtime's local time zone.

export function classroomDueToDate(dueDate, dueTime) {
  if (!dueDate) return null;
  const { year, month, day } = dueDate;
  if (!dueTime) return { date: new Date(year, month - 1, day), allDay: true };
  const date = new Date(Date.UTC(year, month - 1, day, dueTime.hours || 0, dueTime.minutes || 0));
  return { date, allDay: false };
}

const pad = (n) => String(n).padStart(2, '0');

export function ymd(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function parseYmd(str) {
  const [y, m, d] = str.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function addDays(date, n) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);
}

export function startOfWeek(date) {
  const d = startOfDay(date);
  return addDays(d, -((d.getDay() + 6) % 7));
}

export function sameDay(a, b) {
  return ymd(a) === ymd(b);
}
