// Browser check of demo mode. Usage: node scripts/demo-check.cjs <screenshot-dir>
// Serves homework-calendar/ with python3, opens /?demo=1 in Chromium at phone and desktop sizes,
// then checks offline/blocked/no-cache handling in live mode with Google stubbed out.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const shotDir = path.resolve(process.argv[2] || path.join(ROOT, 'shots'));

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

async function waitForServer(url, ms = 10000) {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    const ok = await new Promise((resolve) => {
      http.get(url, (res) => { res.resume(); resolve(res.statusCode < 500); }).on('error', () => resolve(false));
    });
    if (ok) return;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`server did not start at ${url}`);
}

const failures = [];
function check(label, ok, detail = '') {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}${!ok && detail ? ` (${detail})` : ''}`);
  if (!ok) failures.push(label);
}

async function run(browser, base, width, height) {
  const tag = `${width}x${height}`;
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  // Demo mode never needs Google; stub the sign-in script so the check works offline.
  await page.route('https://accounts.google.com/**', (r) =>
    r.fulfill({ status: 200, contentType: 'text/javascript', body: '' }));

  const res = await page.goto(`${base}/?demo=1`);
  check(`${tag} page loads`, !!res && res.ok(), res ? `status ${res.status()}` : 'no response');
  await page.waitForSelector('#checklist .row', { timeout: 5000 }).catch(() => {});

  const next = (await page.locator('#next').textContent().catch(() => '')) || '';
  check(`${tag} #next shows ⚠ TEST`, next.includes('⚠ TEST'), next.slice(0, 120));
  check(`${tag} #next shows "add a date"`, next.includes('add a date'));
  check(`${tag} an overdue row exists`, (await page.locator('.row.overdue').count()) > 0);
  const late = (await page.locator('#next .overdue').textContent().catch(() => '')) || '';
  check(`${tag} missed quiz is in What's next overdue`, late.includes('Chapter 3 Quiz'), late.slice(0, 120));

  check(`${tag} "Test on Friday!" visible`,
    await page.getByText('Test on Friday!', { exact: true }).first().isVisible().catch(() => false));
  check(`${tag} escaped title visible`,
    await page.getByText('Fractions: 1/2 < 3/4 & more', { exact: true }).first().isVisible().catch(() => false));

  // Tick the first checklist box.
  const first = page.locator('#checklist input[type=checkbox]').first();
  const id = await first.getAttribute('data-id', { timeout: 2000 }).catch(() => null);
  if (id) {
    // Click once by id: the list re-renders and re-sorts, so `first` would move on.
    await page.locator(`#checklist input[data-id="${id}"]`).click();
    const cls = await page.locator(`#checklist input[data-id="${id}"]`)
      .evaluate((el) => el.closest('.row').className).catch(() => '');
    check(`${tag} ticked row is done`, /\bdone\b/.test(cls), cls);
    await page.locator(`#checklist input[data-id="${id}"]`).click();
    const back = await page.locator(`#checklist input[data-id="${id}"]`)
      .evaluate((el) => el.closest('.row').className).catch(() => '');
    check(`${tag} unticking brings it back`, !/\bdone\b/.test(back), back);
  } else {
    check(`${tag} ticked row is done`, false, 'no checkbox');
  }

  // Add "Piano" today at 4pm through the dialog.
  try {
    await page.click('#add-btn', { timeout: 2000 });
    await page.locator('#add').waitFor({ state: 'visible', timeout: 2000 });
    await page.check('#add input[name=kind][value=activity]');
    await page.fill('#add-title', '');
    await page.click('#add-save');
    const err = (await page.locator('#add-error').textContent()) || '';
    check(`${tag} empty name shows inline error`, err.includes('Name is required'), err);
    const today = await page.evaluate(() => {
      const d = new Date();
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    });
    await page.fill('#add-title', 'Piano');
    await page.fill('#add-date', today);
    await page.fill('#add-time', '16:00');
    await page.click('#add-save');
    await page.locator('#add').waitFor({ state: 'hidden', timeout: 2000 });
    const week = (await page.locator('#week').textContent()) || '';
    check(`${tag} Piano shows in #week`, week.includes('Piano') && week.includes('4:00pm'), week.slice(0, 200));
  } catch (e) {
    check(`${tag} add Piano through the dialog`, false, e.message.split('\n')[0]);
  }

  // Week navigation moves by 7 days and changes the label.
  try {
    const before = await page.locator('#week-label').textContent();
    await page.click('#next-week');
    const after = await page.locator('#week-label').textContent();
    await page.click('#prev-week');
    const back = await page.locator('#week-label').textContent();
    check(`${tag} week arrows`, /^[A-Z][a-z]{2} \d+–/.test(before) && after !== before && back === before,
      `${before} / ${after} / ${back}`);
  } catch (e) {
    check(`${tag} week arrows`, false, e.message.split('\n')[0]);
  }

  if (width <= 400) {
    const overflow = await page.evaluate(() =>
      [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    check(`${tag} no horizontal scroll`, overflow[0] <= overflow[1], `${overflow[0]} > ${overflow[1]}`);
  }

  await page.screenshot({ path: path.join(shotDir, `demo-${width}.png`), fullPage: true });

  // Pick a date for the undated test: the "add a date" line goes away.
  try {
    await page.click('#next [data-action=set-date]', { timeout: 2000 });
    await page.locator('#pick-date').waitFor({ state: 'visible', timeout: 2000 });
    const later = await page.evaluate(() => {
      const d = new Date(); d.setDate(d.getDate() + 3);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    });
    await page.fill('#pick-date input[type=date]', later);
    await page.click('#pick-date-save');
    await page.locator('#pick-date').waitFor({ state: 'hidden', timeout: 2000 });
    const nextAfter = (await page.locator('#next').textContent()) || '';
    check(`${tag} picking a test date clears "add a date"`, !nextAfter.includes('add a date'), nextAfter.slice(0, 200));
    // The picked date can be changed: the dialog opens with it filled in.
    await page.click('#next .change-date', { timeout: 2000 });
    await page.locator('#pick-date').waitFor({ state: 'visible', timeout: 2000 });
    const filled = await page.inputValue('#pick-date-input');
    check(`${tag} Change date opens with the picked date`, filled === later, `${filled} vs ${later}`);
    await page.click('#pick-date-cancel');
  } catch (e) {
    check(`${tag} pick a test date`, false, e.message.split('\n')[0]);
  }

  check(`${tag} no console errors`, errors.length === 0, errors.join(' | '));
  await context.close();
}

// ---------- live mode with Google stubbed (no real network) ----------

const FAKE_CONFIG = "export const CLIENT_ID = 'check.apps.googleusercontent.com';";
// A GIS stand-in whose token request succeeds at once. Window flags steer it:
// __gisPopupBlocked (fail like a popup opened without a tap), __gisMissingScopes,
// __gisExpiresIn (seconds). __gisPrompts records each request's prompt.
const FAKE_GIS = `window.__gisPrompts = [];
window.google = { accounts: { oauth2: {
  hasGrantedAllScopes() { return !window.__gisMissingScopes; },
  initTokenClient(o) { return {
    requestAccessToken(r) {
      window.__gisPrompts.push(r && r.prompt);
      setTimeout(() => (window.__gisPopupBlocked
        ? o.error_callback({ type: 'popup_failed_to_open' })
        : o.callback({ access_token: 't', expires_in: window.__gisExpiresIn || 3600 })), 0);
    } }; } } } };`;
const CACHED_RAW = {
  courses: [{ id: 'c1', name: 'Art' }],
  courseWork: [{ id: 'k1', courseId: 'c1', title: 'Cached drawing', alternateLink: 'https://classroom.google.com/x',
    creationTime: new Date().toISOString(), dueDate: (() => {
      const d = new Date(); d.setDate(d.getDate() + 1);
      return { year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate() };
    })() }],
  announcements: [], materials: [],
};

const ymdOf = (d) => ({ year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate() });
const tomorrow = () => { const d = new Date(); d.setDate(d.getDate() + 1); return d; };
// Classroom with one class and two pieces of homework due tomorrow.
const LIVE_RAW = {
  courses: [{ id: 'c1', name: 'Art' }],
  courseWork: ['k1', 'k2'].map((id) => ({ id, courseId: 'c1', title: `Drawing ${id}`,
    alternateLink: 'https://classroom.google.com/x', creationTime: new Date().toISOString(), dueDate: ymdOf(tomorrow()) })),
  announcements: [], materials: [],
};
function classroomOk(r) {
  const url = r.request().url();
  let body = {};
  if (url.includes('/courses?')) body = { courses: LIVE_RAW.courses };
  else if (url.includes('/studentSubmissions')) body = { studentSubmissions: [] };
  else if (url.includes('/courseWork?')) body = { courseWork: LIVE_RAW.courseWork };
  return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
}
// A small in-memory Drive app folder. drive.file: the saved JSON (or null); drive.gate: a promise
// the file lookup waits on; drive.uploads: every upload body.
function fakeDrive(drive) {
  drive.uploads = [];
  return async (r) => {
    const req = r.request(); const url = req.url();
    const json = (status, body) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.startsWith('https://www.googleapis.com/drive/v3/files?')) {
      if (drive.gate) await drive.gate;
      return json(200, { files: drive.file ? [{ id: 'F1' }] : [] });
    }
    if (url.startsWith('https://www.googleapis.com/drive/v3/files/F1?alt=media')) return json(200, drive.file);
    if (url.startsWith('https://www.googleapis.com/upload/drive/v3/files')) {
      const body = req.postData() || '';
      drive.uploads.push(body);
      const content = req.method() === 'PATCH' ? body : body.split('\r\n\r\n')[2].split('\r\n--')[0];
      drive.file = JSON.parse(content);
      return json(200, { id: 'F1' });
    }
    return json(404, {});
  };
}

async function livePage(browser, base, { gis, classroom, drive, cache, state, flags }) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.route('**/config.js', (r) => r.fulfill({ status: 200, contentType: 'text/javascript', body: FAKE_CONFIG }));
  await page.route('https://accounts.google.com/**', (r) => (gis === 'fail'
    ? r.abort()
    : r.fulfill({ status: 200, contentType: 'text/javascript', body: FAKE_GIS })));
  await page.route('https://classroom.googleapis.com/**', (r) => {
    if (classroom === 'blocked') return r.fulfill({ status: 403, contentType: 'application/json', body: '{"error":{"status":"PERMISSION_DENIED"}}' });
    if (classroom === 'ok') return classroomOk(r);
    return r.abort();
  });
  const driveFake = drive && typeof drive === 'object' ? fakeDrive(drive) : null;
  await page.route('https://www.googleapis.com/**', (r) => {
    if (driveFake) return driveFake(r);
    if (drive === 'empty') return r.fulfill({ status: 200, contentType: 'application/json', body: '{"files":[]}' });
    return r.abort();
  });
  if (cache !== undefined || state !== undefined) {
    await page.addInitScript(([c, s]) => {
      if (!sessionStorage.getItem('seeded')) {
        if (c !== null) localStorage.setItem('hc.classroom', c);
        if (s !== null) localStorage.setItem('hc.state', s);
        sessionStorage.setItem('seeded', '1');
      }
    }, [cache ?? null, state ?? null]);
  }
  if (flags) await page.addInitScript((f) => Object.assign(window, f), flags);
  await page.goto(`${base}/`);
  return { context, page, errors };
}

const text = async (page, sel) => ((await page.locator(sel).textContent().catch(() => '')) || '');

async function signInAndSettle(page) {
  await page.waitForFunction(() => !document.getElementById('signin-btn').disabled);
  await page.click('#signin-btn');
  await page.waitForFunction(() => {
    const s = document.getElementById('status');
    return !document.getElementById('app').hidden && !(s.textContent || '').startsWith('Loading');
  });
}

async function runLive(browser, base) {
  const scenario = async (name, opts, fn) => {
    const { context, page, errors } = await livePage(browser, base, opts);
    try { await fn(page, errors); } catch (e) { check(`${name} scenario`, false, e.message.split('\n')[0]); }
    await context.close();
  };
  // 1. Google script can't load, cached Classroom data: shown, and a tick survives a reload.
  await scenario('offline view', { gis: 'fail', cache: JSON.stringify(CACHED_RAW) }, async (page, errors) => {
    // Generous wait: the page also gives up on the Google script after a timeout.
    await page.waitForSelector('#checklist .row', { timeout: 20000 });
    check('offline view shows cached data', (await text(page, '#checklist')).includes('Cached drawing'));
    check('offline view says saved info', (await text(page, '#status')).includes("Showing saved info, can't reach Google right now."));
    await page.click('#checklist input[data-id="cw:k1"]');
    await page.reload();
    await page.waitForSelector('#checklist .row', { timeout: 20000 });
    check('offline tick survives reload', await page.locator('#checklist input[data-id="cw:k1"]').isChecked());
    check('offline view no page errors', errors.length === 0, errors.join(' | '));
  });
  // 2. School blocks the app on first use: blocked message, no "Nice!".
  await scenario('blocked', { classroom: 'blocked', drive: 'empty' }, async (page, errors) => {
    await signInAndSettle(page);
    const status = await text(page, '#status');
    check('blocked message', status === "Your school blocked this app from reading Google Classroom. Ask a parent to contact the school's IT.", status);
    const next = await text(page, '#next'), list = await text(page, '#checklist');
    check('blocked: "Couldn\'t load Classroom." in both sections',
      next.includes("Couldn't load Classroom.") && list.includes("Couldn't load Classroom."));
    check('blocked: no "Nice!"', !next.includes('Nice!') && !list.includes('Nice!'));
    check('blocked no page errors', errors.length === 0, errors.join(' | '));
  });
  // 3. Network down, corrupt cache: treated as no cache.
  await scenario('corrupt cache', { cache: '{"courses":5}' }, async (page, errors) => {
    await signInAndSettle(page);
    const status = await text(page, '#status');
    check('no-cache network message', status === "Can't reach Google right now.", status);
    check('corrupt cache: "Couldn\'t load Classroom."', (await text(page, '#next')).includes("Couldn't load Classroom."));
    check('corrupt cache no page errors', errors.length === 0, errors.join(' | '));
  });
  // 4. The token runs out while the page is open: the background save can't open a popup.
  //    The app stays, says Reconnect, does not retry in a loop; Reconnect (a tap) saves the tick.
  const drive4 = { file: null };
  await scenario('token expiry', { classroom: 'ok', drive: drive4, flags: { __gisExpiresIn: 62 } }, async (page, errors) => {
    await signInAndSettle(page);
    check('sign-in asks with prompt ""', (await page.evaluate(() => window.__gisPrompts)).join('|') === '');
    await page.waitForTimeout(2500); // token now has under 60s left, so it counts as expired
    await page.evaluate(() => { window.__gisPopupBlocked = true; });
    await page.click('#checklist input[data-id="cw:k1"]');
    await page.waitForFunction(() => document.getElementById('status').textContent.includes('Reconnect'), null, { timeout: 6000 });
    check('expiry: app stays visible', await page.isVisible('#app') && !(await page.isVisible('#signin')));
    check('expiry: Reconnect button shown', await page.isVisible('#reconnect'));
    check('expiry: tick still shown', await page.locator('#checklist input[data-id="cw:k1"]').isChecked());
    const asked = (await page.evaluate(() => window.__gisPrompts.length));
    await page.waitForTimeout(4000);
    check('expiry: no retry loop', (await page.evaluate(() => window.__gisPrompts.length)) === asked && drive4.uploads.length === 0,
      `${asked} -> ${await page.evaluate(() => window.__gisPrompts.length)} token requests, ${drive4.uploads.length} uploads`);
    await page.evaluate(() => { window.__gisPopupBlocked = false; });
    await page.click('#reconnect');
    await page.waitForFunction(() => document.getElementById('status-bar').hidden);
    await page.waitForTimeout(300);
    check('expiry: Reconnect saves the tick to Drive', drive4.file && drive4.file.checks && drive4.file.checks['cw:k1'] === true,
      JSON.stringify(drive4.file));
    check('token expiry no page errors', errors.length === 0, errors.join(' | '));
  });
  // 5. A tick made while the first Drive load is still on its way keeps changes from another device.
  let open;
  const drive5 = { file: { version: 1, checks: { 'cw:k2': true }, testDates: {}, myItems: [], updatedAt: 2000 },
    gate: new Promise((r) => { open = r; }) };
  const staleState = JSON.stringify({ version: 1, checks: {}, testDates: {}, myItems: [], updatedAt: 1000 });
  await scenario('tick during first load', { classroom: 'ok', drive: drive5, cache: JSON.stringify(LIVE_RAW), state: staleState },
    async (page, errors) => {
      await page.waitForFunction(() => !document.getElementById('signin-btn').disabled);
      await page.click('#signin-btn');
      await page.waitForSelector('#checklist input[data-id="cw:k1"]');
      await page.click('#checklist input[data-id="cw:k1"]');
      open();
      await page.waitForFunction(() => document.querySelector('#checklist input[data-id="cw:k2"]')?.checked, null, { timeout: 4000 })
        .catch(() => {});
      check('first load: other device\'s tick kept', await page.locator('#checklist input[data-id="cw:k2"]').isChecked());
      check('first load: my tick kept', await page.locator('#checklist input[data-id="cw:k1"]').isChecked());
      await page.waitForTimeout(2200); // debounce, then the save
      const f = drive5.file || {};
      check('first load: Drive gets both ticks', f.checks && f.checks['cw:k1'] === true && f.checks['cw:k2'] === true, JSON.stringify(f));
      check('tick during first load no page errors', errors.length === 0, errors.join(' | '));
    });
  // 6. He left a box unticked: asked to sign in again; the next try asks for consent.
  await scenario('missing scopes', { classroom: 'ok', drive: { file: null }, flags: { __gisMissingScopes: true } }, async (page, errors) => {
    await page.waitForFunction(() => !document.getElementById('signin-btn').disabled);
    await page.click('#signin-btn');
    await page.waitForFunction(() => document.getElementById('status').textContent.length > 0);
    check('scopes: message', (await text(page, '#status')) === 'Please sign in again and tick every box.', await text(page, '#status'));
    check('scopes: still on sign-in screen', await page.isVisible('#signin-btn') && !(await page.isVisible('#app')));
    check('scopes: no "Access blocked" hint', !(await page.isVisible('#signin-hint')));
    await page.evaluate(() => { window.__gisMissingScopes = false; });
    await signInAndSettle(page);
    check('scopes: second try asks for consent', (await page.evaluate(() => window.__gisPrompts)).join('|') === '|consent',
      (await page.evaluate(() => window.__gisPrompts)).join('|'));
    check('missing scopes no page errors', errors.length === 0, errors.join(' | '));
  });
}

// ---------- a page left open overnight catches up when he comes back ----------

async function runWake(browser, base) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, timezoneId: 'America/Los_Angeles' });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  try {
    await page.route('https://accounts.google.com/**', (r) => r.fulfill({ status: 200, contentType: 'text/javascript', body: '' }));
    await page.clock.install({ time: new Date('2026-11-22T23:58:00-08:00') }); // Sunday night
    await page.goto(`${base}/?demo=1`);
    await page.waitForSelector('#checklist .row');
    const before = await text(page, '#week-label');
    await page.clock.setSystemTime(new Date('2026-11-23T07:30:00-08:00')); // Monday morning
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    const after = await text(page, '#week-label');
    const today = await page.getAttribute('#week .day.today', 'data-date').catch(() => null);
    check('wake: week moves to the new week', before === 'Nov 16–22' && after === 'Nov 23–29', `${before} -> ${after}`);
    check('wake: today is Monday', today === '2026-11-23', String(today));
  } catch (e) {
    check('wake scenario', false, e.message.split('\n')[0]);
  }
  await context.close();
}

(async () => {
  fs.mkdirSync(shotDir, { recursive: true });
  const port = await freePort();
  const server = spawn('python3', ['-m', 'http.server', String(port), '--bind', '127.0.0.1'],
    { cwd: ROOT, stdio: 'ignore' });
  let browser;
  try {
    const base = `http://127.0.0.1:${port}`;
    await waitForServer(`${base}/`);
    browser = await chromium.launch();
    await run(browser, base, 390, 844);
    await run(browser, base, 1280, 800);
    await runLive(browser, base);
    await runWake(browser, base);
  } catch (e) {
    check('run', false, e.message);
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
  console.log(failures.length ? `\n${failures.length} check(s) failed` : `\nall checks passed; screenshots in ${shotDir}`);
  process.exit(failures.length ? 1 : 0);
})();
