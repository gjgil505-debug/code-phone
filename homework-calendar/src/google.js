import { normalizeState } from './store.js';

export const SCOPES = [
  'https://www.googleapis.com/auth/classroom.courses.readonly',
  'https://www.googleapis.com/auth/classroom.coursework.me.readonly',
  'https://www.googleapis.com/auth/classroom.announcements.readonly',
  'https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly',
  'https://www.googleapis.com/auth/drive.appdata',
].join(' ');

const CLASSROOM = 'https://classroom.googleapis.com/v1';
const DRIVE = 'https://www.googleapis.com/drive/v3';
const UPLOAD = 'https://www.googleapis.com/upload/drive/v3';
const FILE_NAME = 'homework-calendar.json';

export function classifyGoogleError({ status, body, gisError, networkError } = {}) {
  if (networkError) return 'network';
  if (gisError === 'admin_policy_enforced') return 'blocked';
  if (status === 401) return 'signin';
  if (status === 403 && /ClassroomApiDisabled|admin_policy_enforced|PERMISSION_DENIED|has not been granted/.test(String(body || ''))) return 'blocked';
  if (['popup_closed', 'access_denied', 'popup_failed_to_open'].includes(gisError)) return 'signin';
  return 'other';
}

function makeError(message, kind, status) {
  const err = new Error(message);
  err.kind = kind;
  if (status !== undefined) err.status = status;
  return err;
}

export function createAuth(clientId, google = globalThis.google) {
  // needConsent: he left a box unticked last time, so show Google's full consent screen again.
  let token = null, expiresAt = 0, needConsent = false, pending = null, inflight = null;
  const settle = (fn, v) => { const p = pending; pending = null; if (p) p[fn](v); };
  const oauth2 = google.accounts.oauth2;
  const client = oauth2.initTokenClient({
    client_id: clientId,
    scope: SCOPES,
    callback: (r) => {
      if (r.error) return settle('reject', makeError(r.error, classifyGoogleError({ gisError: r.error })));
      if (!oauth2.hasGrantedAllScopes(r, ...SCOPES.split(' '))) {
        needConsent = true;
        return settle('reject', makeError('not every permission was granted', 'scopes'));
      }
      needConsent = false;
      token = r.access_token;
      expiresAt = Date.now() + Number(r.expires_in || 0) * 1000;
      settle('resolve', token);
    },
    error_callback: (e) => settle('reject', makeError(e.type || 'sign-in failed', classifyGoogleError({ gisError: e.type }))),
  });
  const request = (prompt) => {
    inflight ||= new Promise((resolve, reject) => {
      pending = { resolve, reject };
      client.requestAccessToken({ prompt });
    }).finally(() => { inflight = null; });
    return inflight;
  };
  const hasToken = () => !!token && expiresAt - Date.now() > 60000;
  return {
    // Google shows its consent screen by itself when something is still to be granted.
    signIn() {
      return request(needConsent ? 'consent' : '');
    },
    async getToken() {
      if (hasToken()) return token;
      return request('');
    },
    hasToken,
  };
}

export function createApi(getToken, fetchFn = (...a) => fetch(...a)) {
  let fileId = null;

  async function call(url, opts = {}) {
    const headers = { ...(opts.headers || {}), Authorization: `Bearer ${await getToken()}` };
    let res;
    try {
      res = await fetchFn(url, { ...opts, headers });
    } catch (e) {
      throw makeError('network error', 'network');
    }
    if (!res.ok) {
      let body = '';
      try { body = await res.text(); } catch (e) { /* ignore */ }
      throw makeError(`Google request failed (${res.status})`, classifyGoogleError({ status: res.status, body }), res.status);
    }
    return res;
  }

  async function list(base, key) {
    const out = [];
    let pageToken = '';
    for (let i = 0; i < 3; i++) {
      const sep = base.includes('?') ? '&' : '?';
      const res = await call(base + (pageToken ? `${sep}pageToken=${encodeURIComponent(pageToken)}` : ''));
      const data = await res.json();
      out.push(...(data[key] || []));
      pageToken = data.nextPageToken;
      if (!pageToken) break;
    }
    return out;
  }

  const optional = (p) => p.catch((e) => {
    if (e.status === 403 || e.status === 404) return [];
    throw e;
  });

  async function fetchClassroom() {
    const courses = (await list(`${CLASSROOM}/courses?studentId=me&courseStates=ACTIVE&pageSize=100`, 'courses'))
      .map((c) => ({ id: c.id, name: c.name }));
    const raw = { courses, courseWork: [], announcements: [], materials: [] };
    await Promise.all(courses.map(async ({ id }) => {
      const base = `${CLASSROOM}/courses/${encodeURIComponent(id)}`;
      const [work, subs, ann, mat] = await Promise.all([
        list(`${base}/courseWork?courseWorkStates=PUBLISHED&pageSize=100`, 'courseWork'),
        list(`${base}/courseWork/-/studentSubmissions?userId=me&pageSize=100`, 'studentSubmissions'),
        optional(list(`${base}/announcements?announcementStates=PUBLISHED&pageSize=50`, 'announcements')),
        optional(list(`${base}/courseWorkMaterials?courseWorkMaterialStates=PUBLISHED&pageSize=50`, 'courseWorkMaterial')),
      ]);
      const states = new Map(subs.map((s) => [s.courseWorkId, s.state]));
      for (const w of work) {
        const item = { ...w, courseId: w.courseId || id };
        if (states.has(w.id)) item.submissionState = states.get(w.id);
        raw.courseWork.push(item);
      }
      raw.announcements.push(...ann);
      raw.materials.push(...mat);
    }));
    return raw;
  }

  // Finds the saved file (newest first if there are ever two). Sets fileId; false when there is none.
  async function findFile() {
    if (fileId) return true;
    const q = encodeURIComponent(`name='${FILE_NAME}'`);
    const order = encodeURIComponent('modifiedTime desc');
    const res = await call(`${DRIVE}/files?spaces=appDataFolder&q=${q}&orderBy=${order}&fields=files(id)`);
    const files = (await res.json()).files || [];
    if (files.length) fileId = files[0].id;
    return !!fileId;
  }

  async function loadSaved() {
    if (!(await findFile())) return null;
    const res = await call(`${DRIVE}/files/${fileId}?alt=media`);
    return normalizeState(await res.text());
  }

  async function saveSaved(state) {
    const content = JSON.stringify(state);
    if (await findFile()) {
      await call(`${UPLOAD}/files/${fileId}?uploadType=media`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: content,
      });
      return;
    }
    const boundary = 'hwcal' + Math.random().toString(36).slice(2);
    const body = `--${boundary}\r\nContent-Type: application/json\r\n\r\n`
      + JSON.stringify({ name: FILE_NAME, parents: ['appDataFolder'] })
      + `\r\n--${boundary}\r\nContent-Type: application/json\r\n\r\n${content}\r\n--${boundary}--`;
    const res = await call(`${UPLOAD}/files?uploadType=multipart`, {
      method: 'POST', headers: { 'Content-Type': `multipart/related; boundary=${boundary}` }, body,
    });
    fileId = (await res.json()).id;
  }

  return { fetchClassroom, loadSaved, saveSaved };
}
