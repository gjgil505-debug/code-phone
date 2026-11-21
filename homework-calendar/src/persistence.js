// Local cache plus debounced, serialized sync to the hidden Drive file.
import { emptyState, normalizeState, pickNewer } from './store.js';

const STATE_KEY = 'hc.state';

export function createPersistence({
  storage, api, debounceMs = 1500, setTimer = setTimeout, clearTimer = clearTimeout, onSyncError,
} = {}) {
  let pending = null; // latest state not yet on Drive
  let running = null; // promise of the active Drive save loop
  let timer = null;

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
    const p = (async () => {
      while (pending) {
        const state = pending;
        pending = null;
        try {
          await api.saveSaved(state);
        } catch (err) {
          if (!pending) pending = state; // keep for retry unless superseded
          reportError(err);
          break;
        }
      }
    })().finally(() => {
      if (running === p) running = null;
      // Something is still unsaved after a failure: retry later, not in a tight loop.
      if (pending && timer === null) arm();
    });
    running = p;
    return p;
  }

  function arm() {
    cancelTimer();
    timer = setTimer(() => { timer = null; drive(); }, debounceMs);
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
    writeCache(STATE_KEY, result);
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
