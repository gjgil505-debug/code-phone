// Saved state: pure functions over a plain SavedState object.
import { parseYmd, ymd } from './dates.js';

const KINDS = ['activity', 'test', 'homework'];

export function emptyState() {
  return { version: 1, checks: {}, testDates: {}, myItems: [], updatedAt: 0 };
}

function isPlainObject(x) {
  return x !== null && typeof x === 'object' && !Array.isArray(x);
}

function validDate(s) {
  if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  return ymd(parseYmd(s)) === s;
}

function normalizeItem(it) {
  if (!isPlainObject(it)) return null;
  if (typeof it.id !== 'string' || !it.id) return null;
  if (typeof it.title !== 'string' || !it.title.trim()) return null;
  if (!KINDS.includes(it.kind) || !validDate(it.date)) return null;
  const out = { id: it.id, kind: it.kind, title: it.title.trim(), date: it.date };
  if (typeof it.time === 'string' && /^\d{2}:\d{2}$/.test(it.time)) out.time = it.time;
  if (typeof it.repeatWeekly === 'boolean') out.repeatWeekly = it.repeatWeekly;
  return out;
}

export function normalizeState(raw) {
  let obj = raw;
  if (typeof raw === 'string') {
    try { obj = JSON.parse(raw); } catch { return emptyState(); }
  }
  if (!isPlainObject(obj)) return emptyState();
  const state = emptyState();
  if (isPlainObject(obj.checks)) {
    for (const [k, v] of Object.entries(obj.checks)) if (typeof v === 'boolean') state.checks[k] = v;
  }
  if (isPlainObject(obj.testDates)) {
    for (const [k, v] of Object.entries(obj.testDates)) if (validDate(v)) state.testDates[k] = v;
  }
  if (Array.isArray(obj.myItems)) {
    state.myItems = obj.myItems.map(normalizeItem).filter(Boolean);
  }
  state.updatedAt = Number.isFinite(obj.updatedAt) ? obj.updatedAt : 0;
  return state;
}

export function setCheck(state, id, done, now) {
  return { ...state, checks: { ...state.checks, [id]: !!done }, updatedAt: now };
}

export function setTestDate(state, id, date, now) {
  return { ...state, testDates: { ...state.testDates, [id]: date }, updatedAt: now };
}

function cleanTitle(title) {
  const t = String(title ?? '').trim();
  if (!t) throw new Error('Name is required');
  return t;
}

export function addMyItem(state, fields, now, makeId = () => crypto.randomUUID()) {
  const item = { id: makeId(), kind: fields.kind, title: cleanTitle(fields.title), date: fields.date };
  if (fields.time) item.time = fields.time;
  if (fields.repeatWeekly) item.repeatWeekly = true;
  return { ...state, myItems: [...state.myItems, item], updatedAt: now };
}

export function updateMyItem(state, id, fields, now) {
  if (!state.myItems.some((it) => it.id === id)) return state;
  const patch = { ...fields };
  if ('title' in patch) patch.title = cleanTitle(patch.title);
  const myItems = state.myItems.map((it) => (it.id === id ? { ...it, ...patch, id } : it));
  return { ...state, myItems, updatedAt: now };
}

export function deleteMyItem(state, id, now) {
  const checks = { ...state.checks };
  delete checks['my:' + id];
  return { ...state, checks, myItems: state.myItems.filter((it) => it.id !== id), updatedAt: now };
}

export function pickNewer(a, b) {
  return b.updatedAt > a.updatedAt ? b : a;
}
