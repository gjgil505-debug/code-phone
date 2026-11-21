// DOM wiring: sign-in, loading, rendering and the two dialogs.
import { CLIENT_ID } from '../config.js';
import { ymd, parseYmd, addDays, startOfWeek, sameDay } from './dates.js';
import { buildItems, isTurnedIn } from './items.js';
import { whatsNext, checklist, weekDays } from './summary.js';
import {
  emptyState, setCheck, clearCheck, setTestDate, addMyItem, updateMyItem, deleteMyItem, pickNewer,
} from './store.js';
import { renderWhatsNext, renderWeek, renderChecklist } from './render.js';
import { demoData } from './demo.js';
import { createAuth, createApi } from './google.js';
import { createPersistence } from './persistence.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MSG = {
  blocked: "Your school blocked this app from reading Google Classroom. Ask a parent to contact the school's IT.",
  offline: "Showing saved info, can't reach Google right now.",
  noCache: "Can't reach Google right now.",
  noGoogle: "Can't reach Google right now. Check the internet and reload.",
  other: 'Something went wrong talking to Google. Try Refresh.',
  otherSignIn: 'Something went wrong talking to Google. Try again.',
  reconnect: 'Sign-in ran out. Tap Reconnect to keep saving.',
  scopes: 'Please sign in again and tick every box.',
};
const STALE_MS = 15 * 60 * 1000; // refresh Classroom on coming back after this long
const EMPTY_RAW = { courses: [], courseWork: [], announcements: [], materials: [] };
const CLASSROOM_KEY = 'hc.classroom';
const STATE_KEY = 'hc.state';
const NO_DATA = '<p class="empty missing">Couldn\'t load Classroom.</p>';

const $ = (id) => document.getElementById(id);
const demo = new URLSearchParams(location.search).has('demo');

let raw = null;          // RawData, or null before the first load
let saved = emptyState();
let items = [];
let weekStart = startOfWeek(new Date());
let auth = null;
let api = null;
let persistence = null;  // null in demo mode: state lives in memory only; cache-only when Google can't load
let editingId = null;    // raw id of the item open in the add/edit dialog
let datingId = null;     // item id open in the pick-date dialog
let loadedOnce = false;  // the first Drive load after sign-in has settled
let loadQueue = null;    // edits made while that first load is in flight, replayed onto its result
let lastFetchAt = 0;     // when Classroom last loaded
let renderedDay = null;  // local day (YYYY-MM-DD) of the last render

// ---------- status and screens ----------

function setStatus(text, tone = 'warn', { reconnect = false } = {}) {
  const bar = $('status-bar');
  $('status').textContent = text || '';
  bar.dataset.tone = tone;
  bar.hidden = !text;
  $('reconnect').hidden = !(text && reconnect);
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

// background: nobody tapped (a Drive save, a refresh on coming back). Sign-in trouble then
// keeps the app on screen with a Reconnect button instead of swapping to the sign-in screen.
function handleError(err, { background = false } = {}) {
  const kind = err && err.kind;
  const appShown = !$('app').hidden;
  if (kind === 'signin' || kind === 'scopes') {
    if (background && appShown) {
      setStatus(kind === 'scopes' ? MSG.scopes : MSG.reconnect, 'warn', { reconnect: true });
    } else {
      showSignIn();
      setStatus(kind === 'scopes' ? MSG.scopes : '', 'error');
    }
  } else if (kind === 'blocked') {
    setStatus(MSG.blocked, 'error');
  } else if (kind === 'network') {
    setStatus(raw ? MSG.offline : MSG.noCache);
  } else {
    setStatus(appShown ? MSG.other : MSG.otherSignIn, 'error');
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
  renderedDay = ymd(now);
  items = buildItems(raw || EMPTY_RAW, saved, now);
  const byId = new Map(items.map((i) => [i.id, i]));

  // Without Classroom data, say so instead of "Nothing due"; his own items still show.
  const summary = whatsNext(items, now);
  const anyNext = Object.values(summary).some((list) => list.length);
  $('next-body').innerHTML = (raw ? '' : NO_DATA) + (raw || anyNext ? renderWhatsNext(summary, now) : '');

  $('week-h').textContent = weekHeading(now);
  $('week-label').textContent = rangeLabel(weekStart);
  $('week-body').innerHTML = renderWeek(weekDays(items, weekStart), now);
  for (const el of $('week-body').querySelectorAll('[data-action=edit]')) {
    el.tabIndex = 0;
    el.setAttribute('role', 'button');
    el.title = 'Tap to change';
  }

  const rows = checklist(items, now);
  $('checklist-body').innerHTML = (raw ? '' : NO_DATA) + (rows.length
    ? renderChecklist(rows, now)
    : raw ? '<p class="empty">Nothing on the list. Nice!</p>' : '');
  for (const box of $('checklist-body').querySelectorAll('input[data-action=check]')) {
    if (byId.get(box.dataset.id)?.kind === 'test') box.closest('.row').classList.add('kind-test');
  }
}

// Every change is a function of the saved state, so changes made before the first Drive load
// settles can be replayed onto what Drive had instead of a stale cached copy winning.
function edit(change) {
  saved = change(saved);
  if (loadQueue) loadQueue.push(change);
  else if (persistence) persistence.save(saved);
  render();
}

// What Classroom says about this item: turned in or not.
function classroomDone(id) {
  if (!raw || !id.startsWith('cw:')) return false;
  const w = raw.courseWork.find((x) => `cw:${x.id}` === id);
  return isTurnedIn(w && w.submissionState);
}

function tick(id, done) {
  const now = Date.now();
  // Same as Classroom: forget the manual choice, so a later turn-in still counts.
  const same = !!done === classroomDone(id);
  edit((s) => (same ? clearCheck(s, id, now) : setCheck(s, id, done, now)));
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
    const now = Date.now();
    if (editingId) {
      // store.updateMyItem merges, so cleared fields are passed as undefined to drop them.
      const fields = { kind, title, date, time: time || undefined, repeatWeekly: repeat || undefined };
      const id = editingId;
      edit((s) => updateMyItem(s, id, fields, now));
    } else {
      const fields = { kind, title, date };
      if (time) fields.time = time;
      if (repeat) fields.repeatWeekly = true;
      const id = crypto.randomUUID();
      edit((s) => addMyItem(s, fields, now, () => id));
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
  $('pick-date-input').value = item.datePicked && item.dueAt ? ymd(item.dueAt) : '';
  $('pick-date-error').textContent = '';
  $('pick-date').showModal();
}

function savePickDate() {
  const date = $('pick-date-input').value;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    $('pick-date-error').textContent = 'Pick a date';
    return;
  }
  const id = datingId, now = Date.now();
  edit((s) => setTestDate(s, id, date, now));
  $('pick-date').close();
}

// ---------- events ----------

function wireEvents() {
  document.addEventListener('change', (ev) => {
    const box = ev.target.closest?.('[data-action=check]');
    if (box) tick(box.dataset.id, box.checked);
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
    const id = editingId, now = Date.now();
    if (id) edit((s) => deleteMyItem(s, id, now));
    $('add').close();
  });
  $('pick-date-form').addEventListener('submit', (ev) => { ev.preventDefault(); savePickDate(); });
  $('pick-date-cancel').addEventListener('click', () => $('pick-date').close());

  $('reconnect').addEventListener('click', reconnect);

  const flush = () => { if (persistence) persistence.flush(); };
  window.addEventListener('pagehide', flush);
  window.addEventListener('pageshow', wake);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flush();
    else wake();
  });
}

// Back to a page left open: catch up with the date, and with Classroom if it's been a while.
function wake() {
  const now = new Date();
  if (renderedDay && renderedDay !== ymd(now)) {
    if (sameDay(weekStart, startOfWeek(parseYmd(renderedDay)))) weekStart = startOfWeek(now);
    render();
  }
  if (api && auth && lastFetchAt && !$('app').hidden && Date.now() - lastFetchAt > STALE_MS && auth.hasToken()) {
    refresh({ background: true });
  }
}

// ---------- Google ----------

function safeStorage() {
  let storage = null;
  try { storage = window.localStorage; } catch { /* blocked: run without a cache */ }
  return storage;
}

// Cached RawData must have the four arrays of objects, or it is treated as missing.
function readCachedRaw(cache) {
  const x = cache.readCacheRaw(CLASSROOM_KEY);
  const ok = x && typeof x === 'object' && Object.keys(EMPTY_RAW).every((k) =>
    Array.isArray(x[k]) && x[k].every((v) => v !== null && typeof v === 'object'));
  return ok ? x : null;
}

function waitForGis(timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const until = Date.now() + timeoutMs;
    (function poll() {
      if (window.google?.accounts?.oauth2) return resolve(window.google);
      if (window.gisFailed) return reject(new Error('Google sign-in script failed to load'));
      if (Date.now() > until) return reject(new Error('Google sign-in script did not load'));
      setTimeout(poll, 100);
    })();
  });
}

// Ends the first-load queue: replays the edits made meanwhile onto the loaded state and saves them.
function endLoadQueue(loadedState) {
  const queue = loadQueue;
  loadQueue = null;
  loadedOnce = true;
  if (!queue) return;
  let next = loadedState ? pickNewer(queue.base, loadedState) : queue.base;
  for (const change of queue) next = change(next);
  saved = next;
  if (queue.length && persistence) persistence.save(saved);
}

let refreshing = null;
function refresh({ background = false } = {}) {
  refreshing ||= (async () => {
    const btn = $('refresh');
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    if (!raw) setStatus('Loading…', 'info');
    if (!loadedOnce && !loadQueue) loadQueue = Object.assign([], { base: saved });
    try {
      const [loaded, fresh] = await Promise.allSettled([persistence.load(), api.fetchClassroom(new Date())]);
      const loadedState = loaded.status === 'fulfilled' ? loaded.value : null;
      if (loadQueue) endLoadQueue(loadedState);
      else if (loadedState) saved = pickNewer(saved, loadedState);
      if (fresh.status === 'fulfilled') {
        raw = fresh.value;
        lastFetchAt = Date.now();
        persistence.writeCache(CLASSROOM_KEY, raw);
        setStatus('');
      } else {
        handleError(fresh.reason, { background });
      }
      render();
    } finally {
      if (loadQueue) endLoadQueue(null);
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
      refreshing = null;
    }
  })();
  return refreshing;
}

// The Reconnect button: a tap, so Google may open its sign-in popup. Then send what's waiting.
async function reconnect() {
  const btn = $('reconnect');
  btn.disabled = true;
  try {
    await auth.signIn();
  } catch (err) {
    handleError(err, { background: true });
    return;
  } finally {
    btn.disabled = false;
  }
  setStatus('');
  await persistence.flush();
}

async function signIn() {
  try {
    await auth.signIn();
  } catch (err) {
    // The 'Access blocked' hint only makes sense after a sign-in that failed or was closed.
    showSignIn({ hint: err.kind === 'signin' });
    if (err.kind === 'scopes') setStatus(MSG.scopes, 'error');
    else if (err.kind === 'signin') setStatus('');
    else handleError(err);
    return;
  }
  setStatus('');
  showApp();
  persistence.flush(); // anything left unsaved while signed out
  if (!raw) {
    raw = readCachedRaw(persistence);
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
    // Changes are kept in the local cache; the next signed-in load prefers the newer copy and syncs it.
    const cache = createPersistence({ storage: safeStorage(), api: null });
    raw = readCachedRaw(cache);
    if (raw) {
      saved = cache.readCache();
      persistence = { save: (state) => cache.writeCache(STATE_KEY, state), flush: async () => {} };
      showApp();
      $('refresh').hidden = true;
      render();
      setStatus(MSG.offline);
    } else {
      setStatus(MSG.noGoogle);
    }
    return;
  }
  auth = createAuth(CLIENT_ID, google);
  api = createApi(auth.getToken);
  persistence = createPersistence({
    storage: safeStorage(), api, onSyncError: (err) => handleError(err, { background: true }),
  });
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
