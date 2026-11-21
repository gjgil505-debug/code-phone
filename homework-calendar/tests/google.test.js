import test from 'node:test';
import assert from 'node:assert/strict';
import { SCOPES, classifyGoogleError, createApi, createAuth } from '../src/google.js';

const res = (body, status = 200) => ({
  ok: status >= 200 && status < 300, status,
  json: async () => body, text: async () => typeof body === 'string' ? body : JSON.stringify(body),
});

function fake(routes) {
  const calls = [];
  const fn = async (url, opts = {}) => {
    calls.push({ url, opts });
    for (const [match, handler] of routes) {
      if (url.includes(match)) return typeof handler === 'function' ? handler(url, opts) : handler;
    }
    return res({});
  };
  fn.calls = calls;
  return fn;
}
const tok = async () => 'TOK';

test('SCOPES has five scopes', () => {
  assert.equal(SCOPES.split(' ').length, 5);
  assert.ok(SCOPES.includes('drive.appdata'));
});

test('classifyGoogleError cases', () => {
  assert.equal(classifyGoogleError({status:403, body:'{"error":{"status":"PERMISSION_DENIED","message":"@ClassroomApiDisabled"}}'}), 'blocked');
  assert.equal(classifyGoogleError({status:401}), 'signin');
  assert.equal(classifyGoogleError({gisError:'popup_closed'}), 'signin');
  assert.equal(classifyGoogleError({networkError:true}), 'network');
  assert.equal(classifyGoogleError({status:500}), 'other');
  assert.equal(classifyGoogleError({gisError:'admin_policy_enforced'}), 'blocked');
});

test('fetchClassroom merges submission states and follows one nextPageToken', async () => {
  const f = fake([
    ['/courses?studentId', res({ courses: [{ id: 'c1', name: 'Math' }] })],
    ['/courseWork/-/studentSubmissions', res({ studentSubmissions: [{ courseWorkId: 'w1', state: 'TURNED_IN' }] })],
    ['/courseWork?', (url) => url.includes('pageToken=p2')
      ? res({ courseWork: [{ id: 'w2', courseId: 'c1', title: 'B' }] })
      : res({ courseWork: [{ id: 'w1', courseId: 'c1', title: 'A' }], nextPageToken: 'p2' })],
    ['/announcements', res({ announcements: [{ id: 'a1', courseId: 'c1', text: 'hi' }] })],
    ['/courseWorkMaterials', res({ courseWorkMaterial: [{ id: 'm1', courseId: 'c1', title: 'M' }] })],
  ]);
  const raw = await createApi(tok, f).fetchClassroom(new Date());
  assert.deepEqual(raw.courses, [{ id: 'c1', name: 'Math' }]);
  assert.equal(raw.courseWork.length, 2);
  assert.equal(raw.courseWork.find(w => w.id === 'w1').submissionState, 'TURNED_IN');
  assert.equal(raw.courseWork.find(w => w.id === 'w2').submissionState, undefined);
  assert.equal(raw.announcements.length, 1);
  assert.equal(raw.materials[0].id, 'm1');
  assert.ok(f.calls.every(c => c.opts.headers.Authorization === 'Bearer TOK'));
});

test('fetchClassroom skips a 404 on materials for one course', async () => {
  const f = fake([
    ['/courses?studentId', res({ courses: [{ id: 'c1', name: 'Math' }] })],
    ['/courseWorkMaterials', res({ error: {} }, 404)],
  ]);
  const raw = await createApi(tok, f).fetchClassroom(new Date());
  assert.deepEqual(raw.materials, []);
});

test('loadSaved returns null when no file; saveSaved creates then patches', async () => {
  const f = fake([
    ['drive/v3/files?spaces', res({ files: [] })],
    ['uploadType=multipart', res({ id: 'F1' })],
    ['uploadType=media', res({ id: 'F1' })],
  ]);
  const api = createApi(tok, f);
  assert.equal(await api.loadSaved(), null);
  const state = { version: 1, checks: {}, testDates: {}, myItems: [], updatedAt: 5 };
  await api.saveSaved(state);
  await api.saveSaved(state);
  const last = f.calls.slice(-2);
  assert.equal(last[0].opts.method, 'POST');
  assert.ok(last[0].opts.headers['Content-Type'].startsWith('multipart/related; boundary='));
  assert.ok(last[0].opts.body.includes('appDataFolder'));
  assert.equal(last[1].opts.method, 'PATCH');
  assert.ok(last[1].url.includes('/files/F1?uploadType=media'));
});

test('saveSaved looks for an existing file before creating one', async () => {
  const f = fake([
    ['drive/v3/files?spaces', res({ files: [{ id: 'F7' }] })],
    ['uploadType=media', res({ id: 'F7' })],
  ]);
  const state = { version: 1, checks: {}, testDates: {}, myItems: [], updatedAt: 5 };
  await createApi(tok, f).saveSaved(state);
  assert.ok(f.calls[0].url.includes('drive/v3/files?spaces=appDataFolder'));
  assert.ok(f.calls[0].url.includes('orderBy=modifiedTime%20desc') || f.calls[0].url.includes('orderBy=modifiedTime+desc'));
  assert.equal(f.calls.length, 2);
  assert.equal(f.calls[1].opts.method, 'PATCH');
  assert.ok(f.calls[1].url.includes('/files/F7?uploadType=media'));
  assert.ok(!f.calls.some((c) => c.url.includes('uploadType=multipart')));
});

test('after a failed first load, saveSaved still finds the file instead of making a second one', async () => {
  let down = true;
  const f = fake([
    ['drive/v3/files?spaces', () => { if (down) throw new TypeError('offline'); return res({ files: [{ id: 'F8' }] }); }],
    ['uploadType=media', res({ id: 'F8' })],
  ]);
  const api = createApi(tok, f);
  await assert.rejects(api.loadSaved(), (e) => e.kind === 'network');
  down = false;
  await api.saveSaved({ version: 1, checks: {}, testDates: {}, myItems: [], updatedAt: 6 });
  assert.ok(!f.calls.some((c) => c.url.includes('uploadType=multipart')));
  assert.ok(f.calls.at(-1).url.includes('/files/F8?uploadType=media'));
});

test('loadSaved reads an existing file', async () => {
  const f = fake([
    ['drive/v3/files?spaces', res({ files: [{ id: 'F9' }] })],
    ['/files/F9?alt=media', res({ version: 1, checks: { 'cw:1': true }, testDates: {}, myItems: [], updatedAt: 3 })],
  ]);
  const s = await createApi(tok, f).loadSaved();
  assert.equal(s.checks['cw:1'], true);
});

test('403 on courses throws kind blocked; rejected fetch is network', async () => {
  const f = fake([['/courses?studentId', res('{"error":{"status":"PERMISSION_DENIED"}}', 403)]]);
  await assert.rejects(createApi(tok, f).fetchClassroom(new Date()), e => e.kind === 'blocked' && e.status === 403);
  const bad = async () => { throw new TypeError('x'); };
  await assert.rejects(createApi(tok, bad).loadSaved(), e => e.kind === 'network');
});

function fakeGoogle() {
  const g = { requests: [], granted: true, scopeChecks: [] };
  g.google = { accounts: { oauth2: {
    initTokenClient: (cfg) => {
      g.cfg = cfg;
      return { requestAccessToken: (o) => g.requests.push(o) };
    },
    hasGrantedAllScopes: (resp, ...scopes) => { g.scopeChecks.push({ resp, scopes }); return g.granted; },
  } } };
  return g;
}

test('signIn asks with prompt "" so Google shows consent only when needed', async () => {
  const g = fakeGoogle();
  const auth = createAuth('id', g.google);
  for (let n = 0; n < 2; n++) {
    const p = auth.signIn();
    g.cfg.callback({ access_token: 'T' + n, expires_in: 3600 });
    await p;
  }
  assert.deepEqual(g.requests.map((r) => r.prompt), ['', '']);
});

test('missing scopes reject with kind scopes, keep no token, and the next signIn asks for consent', async () => {
  const g = fakeGoogle();
  const auth = createAuth('id', g.google);
  g.granted = false;
  const p1 = auth.signIn();
  g.cfg.callback({ access_token: 'PART', expires_in: 3600, scope: 'x' });
  await assert.rejects(p1, (e) => e.kind === 'scopes');
  assert.deepEqual(g.scopeChecks[0].scopes, SCOPES.split(' '));
  assert.equal(g.scopeChecks[0].resp.access_token, 'PART');
  assert.equal(auth.hasToken(), false);
  g.granted = true;
  const p2 = auth.signIn();
  g.cfg.callback({ access_token: 'FULL', expires_in: 3600 });
  assert.equal(await p2, 'FULL');
  assert.equal(auth.hasToken(), true);
  const p3 = auth.signIn();
  g.cfg.callback({ access_token: 'AGAIN', expires_in: 3600 });
  await p3;
  assert.deepEqual(g.requests.map((r) => r.prompt), ['', 'consent', '']);
});

test('hasToken is false until a token with time left arrives', async () => {
  const g = fakeGoogle();
  const auth = createAuth('id', g.google);
  assert.equal(auth.hasToken(), false);
  const p = auth.getToken();
  g.cfg.callback({ access_token: 'SHORT', expires_in: 30 });
  await p;
  assert.equal(auth.hasToken(), false);
});

test('concurrent getToken makes one request and shares the token', async () => {
  const g = fakeGoogle();
  const auth = createAuth('id', g.google);
  const p1 = auth.getToken(), p2 = auth.getToken();
  assert.equal(g.requests.length, 1);
  g.cfg.callback({ access_token: 'T1', expires_in: 3600 });
  assert.deepEqual(await Promise.all([p1, p2]), ['T1', 'T1']);
});

test('cached token with time left needs no request', async () => {
  const g = fakeGoogle();
  const auth = createAuth('id', g.google);
  const p = auth.getToken();
  g.cfg.callback({ access_token: 'T1', expires_in: 3600 });
  await p;
  assert.equal(await auth.getToken(), 'T1');
  assert.equal(g.requests.length, 1);
});

test('error_callback popup_closed rejects with kind signin', async () => {
  const g = fakeGoogle();
  const p = createAuth('id', g.google).signIn();
  g.cfg.error_callback({ type: 'popup_closed' });
  await assert.rejects(p, (e) => e.kind === 'signin');
});

test('late callback with nothing pending does not throw', () => {
  const g = fakeGoogle();
  createAuth('id', g.google);
  assert.doesNotThrow(() => g.cfg.callback({ access_token: 'x', expires_in: 1 }));
  assert.doesNotThrow(() => g.cfg.error_callback({ type: 'popup_closed' }));
});
