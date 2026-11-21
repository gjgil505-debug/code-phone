import test from 'node:test';
import assert from 'node:assert/strict';
import { SCOPES, classifyGoogleError, createApi } from '../src/google.js';

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
