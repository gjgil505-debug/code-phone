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
  let token = null, expiresAt = 0, asked = false, pending = null, inflight = null;
  const settle = (fn, v) => { const p = pending; pending = null; if (p) p[fn](v); };
  const client = google.accounts.oauth2.initTokenClient({
    client_id: clientId,
    scope: SCOPES,
    callback: (r) => {
      if (r.error) return settle('reject', makeError(r.error, classifyGoogleError({ gisError: r.error })));
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
  return {
    signIn() {
      const prompt = asked ? '' : 'consent';
      asked = true;
      return request(prompt);
    },
    async getToken() {
      if (token && expiresAt - Date.now() > 60000) return token;
      return request('');
    },
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

  async function loadSaved() {
    if (!fileId) {
      const q = encodeURIComponent(`name='${FILE_NAME}'`);
      const res = await call(`${DRIVE}/files?spaces=appDataFolder&q=${q}&fields=files(id)`);
      const files = (await res.json()).files || [];
      if (!files.length) return null;
      fileId = files[0].id;
    }
    const res = await call(`${DRIVE}/files/${fileId}?alt=media`);
    return normalizeState(await res.text());
  }

  async function saveSaved(state) {
    const content = JSON.stringify(state);
    if (fileId) {
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
