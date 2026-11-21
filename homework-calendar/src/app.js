// DOM wiring: sign-in, loading, rendering and the two dialogs.
import { CLIENT_ID } from '../config.js';
import { ymd, parseYmd, addDays, startOfWeek, sameDay } from './dates.js';
import { buildItems } from './items.js';
import { whatsNext, checklist, weekDays } from './summary.js';
import { emptyState, setCheck, setTestDate, addMyItem, updateMyItem, deleteMyItem, pickNewer } from './store.js';
import { renderWhatsNext, renderWeek, renderChecklist } from './render.js';
import { demoData } from './demo.js';
import { createAuth, createApi } from './google.js';
import { createPersistence } from './persistence.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MSG = {
  blocked: "Your school blocked this app from reading Google Classroom. Ask a parent to contact the school's IT.",
  offline: "Showing saved info, can't reach Google right now.",
  noGoogle: "Can't reach Google right now. Check the internet and reload.",
  other: 'Something went wrong talking to Google. Try Refresh.',
};
const EMPTY_RAW = { courses: [], courseWork: [], announcements: [], materials: [] };
const CLASSROOM_KEY = 'hc.classroom';

const $ = (id) => document.getElementById(id);
const demo = new URLSearchParams(location.search).has('demo');

let raw = null;          // RawData, or null before the first load
let saved = emptyState();
let items = [];
let weekStart = startOfWeek(new Date());
let auth = null;
let api = null;
let persistence = null;  // null in demo mode: state lives in memory only
let editingId = null;    // raw id of the item open in the add/edit dialog
let datingId = null;     // item id open in the pick-date dialog

// ---------- status and screens ----------

function setStatus(text, tone = 'warn') {
  const el = $('status');
  el.textContent = text || '';
  el.dataset.tone = tone;
  el.hidden = !text;
}

function showApp() {
  $('signin').hidden = true;
  $('app').hidden = false;
  $('top-buttons').hidden = false;
}

function showSignIn({ hint = false } = {}) {
  $('app').hidden = true;
  $('top-buttons').hidden = true;
  $('signin').hidden = false;
  $('signin-hint').hidden = !hint;
}

function handleError(err) {
  const kind = err && err.kind;
  if (kind === 'signin') {
    setStatus('');
    showSignIn({ hint: true });
  } else if (kind === 'blocked') {
    setStatus(MSG.blocked, 'error');
  } else if (kind === 'network') {
    setStatus(MSG.offline);
  } else {
    setStatus(MSG.other, 'error');
  }
}

// ---------- rendering ----------

function rangeLabel(start) {
  const end = addDays(start, 6);
  const a = `${MONTHS[start.getMonth()]} ${start.getDate()}`;
  return start.getMonth() === end.getMonth()
    ? `${a}–${end.getDate()}`
    : `${a}–${MONTHS[end.getMonth()]} ${end.getDate()}`;
}

function weekHeading(now) {
  const thisWeek = startOfWeek(now);
  if (sameDay(weekStart, thisWeek)) return 'This week';
  if (sameDay(weekStart, addDays(thisWeek, 7))) return 'Next week';
  if (sameDay(weekStart, addDays(thisWeek, -7))) return 'Last week';
  return 'Week';
}

function render() {
  const now = new Date();
  items = buildItems(raw || EMPTY_RAW, saved, now);
  const byId = new Map(items.map((i) => [i.id, i]));

  $('next-body').innerHTML = renderWhatsNext(whatsNext(items, now), now);

  $('week-h').textContent = weekHeading(now);
  $('week-label').textContent = rangeLabel(weekStart);
  $('week-body').innerHTML = renderWeek(weekDays(items, weekStart), now);
  for (const el of $('week-body').querySelectorAll('[data-action=edit]')) {
    el.tabIndex = 0;
    el.setAttribute('role', 'button');
    el.title = 'Tap to change';
  }

  const rows = checklist(items, now);
  $('checklist-body').innerHTML = rows.length
    ? renderChecklist(rows, now)
    : '<p class="empty">Nothing on the list. Nice!</p>';
  for (const box of $('checklist-body').querySelectorAll('input[data-action=check]')) {
    if (byId.get(box.dataset.id)?.kind === 'test') box.closest('.row').classList.add('kind-test');
  }
}

function commit(next) {
  saved = next;
  if (persistence) persistence.save(saved);
  render();
}

// ---------- add / edit dialog ----------

function kindValue() {
  return $('add-form').querySelector('input[name=kind]:checked')?.value || 'activity';
}

function syncRepeatField() {
  $('add-repeat-field').hidden = kindValue() !== 'activity';
}

function openAddDialog(item = null) {
  const form = $('add-form');
  form.reset();
  editingId = item ? item.id : null;
  $('add-h').textContent = item ? 'Change it' : 'Add something';
  const kind = item ? item.kind : 'activity';
  form.querySelector(`input[name=kind][value="${kind}"]`).checked = true;
  $('add-title').value = item ? item.title : '';
  $('add-date').value = item ? item.date : ymd(new Date());
  $('add-time').value = item?.time || '';
  $('add-repeat').checked = !!item?.repeatWeekly;
  $('add-delete').hidden = !item;
  $('add-error').textContent = '';
  syncRepeatField();
  $('add').showModal();
  if (!item) $('add-title').focus();
}

function saveAddDialog() {
  const kind = kindValue();
  const title = $('add-title').value;
  const date = $('add-date').value;
  const time = $('add-time').value;
  const repeat = kind === 'activity' && $('add-repeat').checked;
  let error = '';
  if (!title.trim()) error = 'Name is required';
  else if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || ymd(parseYmd(date)) !== date) error = 'Pick a date';
  if (error) {
    $('add-error').textContent = error;
    return;
  }
  try {
    if (editingId) {
      // store.updateMyItem merges, so cleared fields are passed as undefined to drop them.
      const fields = { kind, title, date, time: time || undefined, repeatWeekly: repeat || undefined };
      commit(updateMyItem(saved, editingId, fields, Date.now()));
    } else {
      const fields = { kind, title, date };
      if (time) fields.time = time;
      if (repeat) fields.repeatWeekly = true;
      commit(addMyItem(saved, fields, Date.now()));
    }
  } catch (err) {
    $('add-error').textContent = err.message;
    return;
  }
  $('add').close();
}

// ---------- pick-date dialog ----------

function openPickDate(item) {
  datingId = item.id;
  $('pick-date-what').textContent = item.courseName ? `${item.courseName}: ${item.title}` : item.title;
  $('pick-date-input').value = '';
  $('pick-date-error').textContent = '';
  $('pick-date').showModal();
}

function savePickDate() {
  const date = $('pick-date-input').value;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    $('pick-date-error').textContent = 'Pick a date';
    return;
  }
  commit(setTestDate(saved, datingId, date, Date.now()));
  $('pick-date').close();
}

// ---------- events ----------

function wireEvents() {
  document.addEventListener('change', (ev) => {
    const box = ev.target.closest?.('[data-action=check]');
    if (box) commit(setCheck(saved, box.dataset.id, box.checked, Date.now()));
  });

  const openEdit = (el) => {
    const id = el.dataset.id.replace(/^my:/, '');
    const mine = saved.myItems.find((m) => m.id === id);
    if (mine) openAddDialog(mine);
  };
  document.addEventListener('click', (ev) => {
    const el = ev.target.closest?.('[data-action]');
    if (!el || ev.target.closest('a')) return;
    if (el.dataset.action === 'set-date') {
      const item = items.find((i) => i.id === el.dataset.id);
      if (item) openPickDate(item);
    } else if (el.dataset.action === 'edit') {
      openEdit(el);
    }
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    const el = ev.target.closest?.('[data-action=edit]');
    if (el && ev.target === el) { ev.preventDefault(); openEdit(el); }
  });

  $('prev-week').addEventListener('click', () => { weekStart = addDays(weekStart, -7); render(); });
  $('next-week').addEventListener('click', () => { weekStart = addDays(weekStart, 7); render(); });
  $('add-btn').addEventListener('click', () => openAddDialog());
  $('refresh').addEventListener('click', () => (demo ? render() : refresh()));

  $('add-form').addEventListener('change', (ev) => { if (ev.target.name === 'kind') syncRepeatField(); });
  $('add-form').addEventListener('submit', (ev) => { ev.preventDefault(); saveAddDialog(); });
  $('add-cancel').addEventListener('click', () => $('add').close());
  $('add-delete').addEventListener('click', () => {
    if (editingId) commit(deleteMyItem(saved, editingId, Date.now()));
    $('add').close();
  });
  $('pick-date-form').addEventListener('submit', (ev) => { ev.preventDefault(); savePickDate(); });
  $('pick-date-cancel').addEventListener('click', () => $('pick-date').close());

  const flush = () => { if (persistence) persistence.flush(); };
  window.addEventListener('pagehide', flush);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush(); });
}

// ---------- Google ----------

function safeStorage() {
  let storage = null;
  try { storage = window.localStorage; } catch { /* blocked: run without a cache */ }
  return storage;
}

function waitForGis(timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const until = Date.now() + timeoutMs;
    (function poll() {
      if (window.google?.accounts?.oauth2) return resolve(window.google);
      if (Date.now() > until) return reject(new Error('Google sign-in script did not load'));
      setTimeout(poll, 100);
    })();
  });
}

let refreshing = null;
function refresh() {
  refreshing ||= (async () => {
    const btn = $('refresh');
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    if (!raw) setStatus('Loading…', 'info');
    try {
      const [loaded, fresh] = await Promise.allSettled([persistence.load(), api.fetchClassroom(new Date())]);
      if (loaded.status === 'fulfilled') saved = pickNewer(saved, loaded.value);
      if (fresh.status === 'fulfilled') {
        raw = fresh.value;
        persistence.writeCache(CLASSROOM_KEY, raw);
        setStatus('');
      } else {
        handleError(fresh.reason);
      }
      render();
    } finally {
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
      refreshing = null;
    }
  })();
  return refreshing;
}

async function signIn() {
  try {
    await auth.signIn();
  } catch (err) {
    showSignIn({ hint: true });
    if (err.kind !== 'signin') handleError(err);
    return;
  }
  setStatus('');
  showApp();
  if (!raw) {
    raw = persistence.readCacheRaw(CLASSROOM_KEY);
    saved = pickNewer(saved, persistence.readCache());
    if (raw) render();
  }
  await refresh();
}

async function startLive() {
  showSignIn();
  if (CLIENT_ID.startsWith('PASTE')) {
    $('setup-msg').hidden = false;
    $('signin-btn').hidden = true;
    return;
  }
  const btn = $('signin-btn');
  btn.disabled = true;
  let google;
  try {
    google = await waitForGis();
  } catch {
    // Offline before sign-in: show whatever this device saved last time.
    const storage = safeStorage();
    const cache = createPersistence({ storage, api: null });
    raw = cache.readCacheRaw(CLASSROOM_KEY);
    if (raw) {
      saved = cache.readCache();
      showApp();
      $('top-buttons').hidden = true;
      render();
      setStatus(MSG.offline);
    } else {
      setStatus(MSG.noGoogle);
    }
    return;
  }
  auth = createAuth(CLIENT_ID, google);
  api = createApi(auth.getToken);
  persistence = createPersistence({ storage: safeStorage(), api, onSyncError: handleError });
  btn.disabled = false;
  btn.addEventListener('click', signIn);
}

function startDemo() {
  const data = demoData(new Date());
  raw = data.raw;
  saved = data.saved;
  showApp();
  $('demo-note').hidden = false;
  render();
}

wireEvents();
if (demo) startDemo();
else startLive();
