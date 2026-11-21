import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createPersistence } from '../src/persistence.js';
import { emptyState } from '../src/store.js';

const st = (updatedAt, extra = {}) => ({ ...emptyState(), updatedAt, ...extra });

function fakeStorage() {
  const m = new Map();
  return { m, getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => void m.set(k, String(v)) };
}
function fakeTimers() {
  let id = 0; const t = new Map(); const delays = [];
  return {
    delays,
    setTimer: (fn, ms) => { delays.push(ms); t.set(++id, fn); return id; },
    clearTimer: (i) => void t.delete(i),
    pending: () => t.size,
    fire: () => { const fns = [...t.values()]; t.clear(); fns.forEach((f) => f()); },
  };
}
const tick = () => new Promise((r) => setImmediate(r));
const kindError = (kind) => Object.assign(new Error(kind), { kind });

test('throwing storage is survived', async () => {
  const bad = { getItem() { throw new Error('x'); }, setItem() { throw new Error('x'); } };
  const timers = fakeTimers();
  const api = { loadSaved: async () => st(5), saveSaved: async () => {} };
  for (const storage of [bad, null, undefined]) {
    const p = createPersistence({ storage, api, ...timers });
    assert.deepEqual(p.readCache(), emptyState());
    assert.equal(p.readCacheRaw('hc.classroom'), null);
    p.writeCache('hc.classroom', { a: 1 });
    assert.equal((await p.load()).updatedAt, 5);
    p.save(st(6));
    await p.flush();
  }
});

test('readCache/readCacheRaw/writeCache round trip and broken json', () => {
  const storage = fakeStorage();
  const p = createPersistence({ storage, api: {}, ...fakeTimers() });
  p.writeCache('hc.classroom', { courses: [] });
  assert.deepEqual(p.readCacheRaw('hc.classroom'), { courses: [] });
  storage.setItem('hc.state', '{nope');
  assert.deepEqual(p.readCache(), emptyState());
  assert.equal(p.readCacheRaw('hc.state'), null);
});

test('load prefers the newer of cache and Drive', async () => {
  const storage = fakeStorage();
  storage.setItem('hc.state', JSON.stringify(st(10, { checks: { a: true } })));
  const p1 = createPersistence({ storage, api: { loadSaved: async () => st(20, { checks: { b: true } }) }, ...fakeTimers() });
  assert.deepEqual((await p1.load()).checks, { b: true });
  assert.equal(p1.readCache().updatedAt, 20);
  const p2 = createPersistence({ storage, api: { loadSaved: async () => st(5) }, ...fakeTimers() });
  assert.equal((await p2.load()).updatedAt, 20);
  const p3 = createPersistence({ storage, api: { loadSaved: async () => null }, ...fakeTimers() });
  assert.equal((await p3.load()).updatedAt, 20);
});

test('load falls back to cache when Drive fails', async () => {
  const storage = fakeStorage();
  storage.setItem('hc.state', JSON.stringify(st(10)));
  const errs = [];
  const api = { loadSaved: async () => { throw Object.assign(new Error('n'), { kind: 'network' }); } };
  const p = createPersistence({ storage, api, ...fakeTimers(), onSyncError: (e) => errs.push(e) });
  assert.equal((await p.load()).updatedAt, 10);
  assert.equal(errs.length, 1);
});

test('save debounces to one Drive call', async () => {
  const storage = fakeStorage(); const timers = fakeTimers(); const calls = [];
  const p = createPersistence({ storage, api: { saveSaved: async (s) => void calls.push(s) }, ...timers });
  p.save(st(1)); p.save(st(2)); p.save(st(3));
  assert.equal(p.readCache().updatedAt, 3);
  assert.equal(calls.length, 0);
  assert.equal(timers.pending(), 1);
  timers.fire(); await tick();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].updatedAt, 3);
});

test('failed Drive save retries on flush', async () => {
  const timers = fakeTimers(); const calls = []; let fail = true; const errs = [];
  const api = { saveSaved: async (s) => { calls.push(s); if (fail) throw new Error('offline'); } };
  const p = createPersistence({ storage: fakeStorage(), api, ...timers, onSyncError: (e) => errs.push(e) });
  p.save(st(1));
  timers.fire(); await tick();
  assert.equal(calls.length, 1);
  assert.equal(errs.length, 1);
  await p.flush();
  assert.equal(calls.length, 2);
  fail = false;
  await p.flush();
  assert.equal(calls.length, 3);
  await p.flush();
  assert.equal(calls.length, 3);
});

test('flush with nothing pending does nothing, never rejects, and does not wedge later saves', async () => {
  const timers = fakeTimers(); const calls = []; let fail = true;
  const api = { saveSaved: async (s) => { calls.push(s); if (fail) throw new Error('x'); } };
  const p = createPersistence({ storage: fakeStorage(), api, ...timers });
  await p.flush();
  assert.equal(calls.length, 0);
  p.save(st(1));
  timers.fire(); await tick();
  assert.equal(calls.length, 1);
  await p.flush();
  assert.equal(calls.length, 2);
  fail = false;
  await p.flush();
  assert.equal(calls.length, 3);
});

test('state saved during a failing save is retried via re-armed timer', async () => {
  const timers = fakeTimers(); const calls = []; const rel = [];
  const api = { saveSaved: (s) => { calls.push(s); return new Promise((res, rej) => rel.push({ res, rej })); } };
  const p = createPersistence({ storage: fakeStorage(), api, ...timers, onSyncError() {} });
  p.save(st(1));
  timers.fire(); await tick();
  p.save(st(2));
  const f = p.flush(); // cancels B's timer, waits on A
  rel[0].rej(kindError('network')); await f;
  assert.equal(calls.length, 1);
  assert.equal(timers.pending(), 1, 'retry timer armed');
  timers.fire(); await tick();
  assert.equal(calls.length, 2);
  assert.equal(calls[1].updatedAt, 2);
  rel[1].res(); await tick();
});

test('load pushes a newer cached state to Drive; equal or older does not', async () => {
  const storage = fakeStorage();
  storage.setItem('hc.state', JSON.stringify(st(10)));
  const timers = fakeTimers(); const calls = [];
  const api = { loadSaved: async () => st(5), saveSaved: async (s) => void calls.push(s) };
  const p = createPersistence({ storage, api, ...timers });
  await p.load();
  timers.fire(); await tick();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].updatedAt, 10);
  for (const remote of [st(10), st(20), null]) {
    const t2 = fakeTimers(); const c2 = [];
    const s2 = fakeStorage(); s2.setItem('hc.state', JSON.stringify(st(remote ? 10 : 0)));
    const p2 = createPersistence({ storage: s2, api: { loadSaved: async () => remote, saveSaved: async (s) => void c2.push(s) }, ...t2 });
    await p2.load(); t2.fire(); await tick();
    assert.equal(c2.length, 0);
  }
});

test('Drive saves are serialized and coalesced', async () => {
  const timers = fakeTimers(); const calls = []; let inflight = 0, maxInflight = 0; const releases = [];
  const api = {
    saveSaved: (s) => {
      calls.push(s); inflight++; maxInflight = Math.max(maxInflight, inflight);
      return new Promise((res) => releases.push(() => { inflight--; res(); }));
    },
  };
  const p = createPersistence({ storage: fakeStorage(), api, ...timers });
  p.save(st(1));
  timers.fire(); await tick();
  assert.equal(calls.length, 1);
  p.save(st(2)); p.save(st(3));
  timers.fire(); await tick();
  assert.equal(calls.length, 1, 'must wait for the running save');
  const done = p.flush();
  releases[0](); await tick();
  assert.equal(calls.length, 2);
  releases[1](); await done;
  assert.equal(maxInflight, 1);
  assert.equal(calls.length, 2);
  assert.equal(calls[1].updatedAt, 3);
});

test('network failures retry with a doubling wait up to 60s, reset after a success', async () => {
  const timers = fakeTimers(); let fail = true; const calls = [];
  const api = { saveSaved: async (s) => { calls.push(s); if (fail) throw kindError('network'); } };
  const p = createPersistence({ storage: fakeStorage(), api, ...timers, onSyncError() {} });
  p.save(st(1));
  assert.deepEqual(timers.delays, [1500]);
  for (let n = 0; n < 7; n++) { timers.fire(); await tick(); }
  assert.equal(calls.length, 7);
  assert.deepEqual(timers.delays, [1500, 3000, 6000, 12000, 24000, 48000, 60000, 60000]);
  fail = false;
  timers.fire(); await tick();
  assert.equal(calls.length, 8);
  assert.equal(timers.pending(), 0, 'nothing left to retry');
  fail = true;
  p.save(st(2));
  timers.fire(); await tick();
  assert.equal(timers.delays.at(-1), 3000, 'backoff starts over');
});

test('sign-in, blocked and other failures keep the state but do not retry until the next save or flush', async () => {
  for (const kind of ['signin', 'blocked', 'other', undefined]) {
    const timers = fakeTimers(); let fail = true; const calls = []; const errs = [];
    const api = { saveSaved: async (s) => { calls.push(s); if (fail) throw kindError(kind); } };
    const storage = fakeStorage();
    const p = createPersistence({ storage, api, ...timers, onSyncError: (e) => errs.push(e.kind) });
    p.save(st(1));
    timers.fire(); await tick();
    assert.equal(calls.length, 1, String(kind));
    assert.equal(timers.pending(), 0, `${kind}: no retry timer`);
    assert.deepEqual(errs, [kind]);
    assert.equal(p.readCache().updatedAt, 1);
    fail = false;
    await p.flush();
    assert.equal(calls.length, 2, `${kind}: flush retries`);
    assert.equal(calls[1].updatedAt, 1);
  }
  // A new save also tries again.
  const timers = fakeTimers(); const calls = [];
  const api = { saveSaved: async (s) => { calls.push(s); if (calls.length === 1) throw kindError('signin'); } };
  const p = createPersistence({ storage: fakeStorage(), api, ...timers, onSyncError() {} });
  p.save(st(1)); timers.fire(); await tick();
  p.save(st(2)); timers.fire(); await tick();
  assert.deepEqual(calls.map((c) => c.updatedAt), [1, 2]);
});

test('load does not overwrite the cache while a save is pending or running', async () => {
  for (const running of [false, true]) {
    const storage = fakeStorage();
    storage.setItem('hc.state', JSON.stringify(st(10)));
    const timers = fakeTimers(); let release; const saves = [];
    let releaseSave;
    const api = {
      loadSaved: () => new Promise((r) => { release = r; }),
      saveSaved: (s) => { saves.push(s); return new Promise((r) => { releaseSave = r; }); },
    };
    const p = createPersistence({ storage, api, ...timers });
    const loading = p.load();
    p.save(st(20, { checks: { 'cw:1': true } }));
    if (running) { timers.fire(); await tick(); assert.equal(saves.length, 1); }
    release(st(15, { checks: { other: true } }));
    const result = await loading;
    assert.equal(result.updatedAt, 15);
    assert.equal(p.readCache().updatedAt, 20, `running=${running}: cache keeps the tick`);
    assert.deepEqual(p.readCache().checks, { 'cw:1': true });
    const f = p.flush(); await tick();
    releaseSave(); await f;
  }
});
