// Local cache plus debounced, serialized sync to the hidden Drive file.
import { emptyState, normalizeState, pickNewer } from './store.js';

const STATE_KEY = 'hc.state';

export function createPersistence({
  storage, api, debounceMs = 1500, maxRetryMs = 60000,
  setTimer = setTimeout, clearTimer = clearTimeout, onSyncError,
} = {}) {
  let pending = null; // latest state not yet on Drive
  let running = null; // promise of the active Drive save loop
  let timer = null;
  let retryMs = 0;    // wait before the next retry after network failures; 0 after a success

  function readCacheRaw(key) {
    try {
      const s = storage.getItem(key);
      return s == null ? null : JSON.parse(s);
    } catch { return null; }
  }
  function writeCache(key, value) {
    try { storage.setItem(key, JSON.stringify(value)); } catch { /* cache is optional */ }
  }
  function readCache() {
    return normalizeState(readCacheRaw(STATE_KEY));
  }
  function reportError(err) {
    try { onSyncError?.(err); } catch { /* ignore */ }
  }

  function drive() {
    if (running) return running;
    if (!pending) return Promise.resolve();
    let failure = null;
    const p = (async () => {
      while (pending) {
        const state = pending;
        pending = null;
        try {
          await api.saveSaved(state);
          retryMs = 0;
        } catch (err) {
          if (!pending) pending = state; // keep for retry unless superseded
          failure = err;
          reportError(err);
          break;
        }
      }
    })().finally(() => {
      if (running === p) running = null;
      // Only a network failure retries by itself, waiting longer each time. Sign-in, blocked and
      // other failures keep the state until the next save or flush (a retry would fail the same way,
      // and a sign-in retry would try to open a popup with nobody tapping).
      if (pending && timer === null && failure?.kind === 'network') {
        retryMs = Math.min(retryMs ? retryMs * 2 : debounceMs * 2, maxRetryMs);
        arm(retryMs);
      }
    });
    running = p;
    return p;
  }

  function arm(ms = debounceMs) {
    cancelTimer();
    timer = setTimer(() => { timer = null; drive(); }, ms);
  }

  function cancelTimer() {
    if (timer !== null) { clearTimer(timer); timer = null; }
  }

  async function load() {
    const cached = readCache();
    let remote = null;
    try {
      remote = await api.loadSaved();
    } catch (err) {
      reportError(err);
      return cached;
    }
    const remoteState = remote ? normalizeState(remote) : emptyState();
    const result = pickNewer(cached, remoteState);
    // A save made while loading is newer and already cached: don't put the older state back.
    if (!pending && !running) writeCache(STATE_KEY, result);
    if (result.updatedAt > remoteState.updatedAt && !pending) {
      pending = result; // local is newer than Drive: push it
      arm();
    }
    return result;
  }

  function save(state) {
    writeCache(STATE_KEY, state);
    pending = state;
    arm();
  }

  async function flush() {
    cancelTimer();
    try { await drive(); } catch { /* never rejects */ }
  }

  return { readCache, readCacheRaw, writeCache, load, save, flush };
}
