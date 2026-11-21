// Renderers: return HTML strings only. Every outside string is escaped.
import { startOfDay, addDays, sameDay, ymd } from './dates.js';
import { isOverdue } from './summary.js';

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const e = escapeHtml;

function timeLabel(d) {
  const h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, '0');
  return `${h % 12 || 12}:${m}${h < 12 ? 'am' : 'pm'}`;
}

function dayLabel(date, now) {
  const diff = Math.round((startOfDay(date) - startOfDay(now)) / 86400000);
  if (diff === 0) return 'today';
  if (diff === 1) return 'tomorrow';
  if (diff > 1 && diff <= 6) return DAYS[date.getDay()];
  return `${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

function titleHtml(item) {
  const t = e(item.title);
  return item.link && /^https:\/\//i.test(item.link) ? `<a href="${e(item.link)}" target="_blank" rel="noopener">${t}</a>` : t;
}

function courseHtml(item) {
  return item.courseName ? `<span class="course">${e(item.courseName)}</span> ` : '';
}

export function renderWhatsNext(summary, now) {
  const parts = [];
  const list = (cls, heading, items, line) => {
    if (!items.length) return;
    parts.push(`<section class="${cls}"><h3>${heading}</h3><ul>${items.map((i) => `<li>${line(i)}</li>`).join('')}</ul></section>`);
  };
  list('tests', 'Tests', summary.tests, (i) =>
    `<span class="test-line">⚠ TEST ${e(dayLabel(i.dueAt, now))}: ${titleHtml(i)}</span> ${courseHtml(i)}`);
  list('needs-date', 'Add a date', summary.needsDate, (i) =>
    `<span>Test mentioned in ${e(i.courseName)}: add a date</span> <button type="button" data-action="set-date" data-id="${e(i.id)}">Add date</button>`);
  const plain = (i) => `${courseHtml(i)}${titleHtml(i)}`;
  list('overdue', 'Overdue', summary.overdue, plain);
  list('today', 'Due today', summary.today, plain);
  list('tomorrow', 'Due tomorrow', summary.tomorrow, plain);
  return parts.length ? parts.join('') : '<p class="empty">Nothing due. Nice!</p>';
}

export function renderWeek(days, now) {
  return days.map(({ date, items }) => {
    const cls = sameDay(date, now) ? 'day today' : 'day';
    const head = `<h3>${e(DAYS[date.getDay()].slice(0, 3))} ${MONTHS[date.getMonth()]} ${date.getDate()}</h3>`;
    const body = items.map((i) => {
      const c = ['item', `kind-${i.kind}`];
      if (i.done) c.push('done');
      if (isOverdue(i, now)) c.push('overdue');
      const label = i.kind === 'test' ? '<strong class="label">TEST</strong> ' : '';
      const time = i.kind === 'activity' && i.dueAt && !i.allDay ? ` <span class="time">${timeLabel(i.dueAt)}</span>` : '';
      const edit = i.source === 'mine' ? ` data-action="edit" data-id="${e(i.id)}"` : '';
      return `<div class="${c.join(' ')}"${edit}>${label}${courseHtml(i)}${titleHtml(i)}${time}</div>`;
    }).join('');
    return `<div class="${cls}" data-date="${ymd(date)}">${head}${body}</div>`;
  }).join('');
}

export function renderChecklist(rows, now) {
  return rows.map(({ item, status }) => {
    const due = item.dueAt ? dayLabel(item.dueAt, now) : 'no date';
    return `<label class="row ${e(status)}"><input type="checkbox" data-action="check" data-id="${e(item.id)}"${item.done ? ' checked' : ''}> ` +
      `${courseHtml(item)}<span class="title">${titleHtml(item)}</span> <span class="due">${e(due)}</span></label>`;
  }).join('');
}
