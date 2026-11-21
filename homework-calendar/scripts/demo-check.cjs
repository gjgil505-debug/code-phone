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
  } catch (e) {
    check(`${tag} pick a test date`, false, e.message.split('\n')[0]);
  }

  check(`${tag} no console errors`, errors.length === 0, errors.join(' | '));
  await context.close();
}

// ---------- live mode with Google stubbed (no real network) ----------

const FAKE_CONFIG = "export const CLIENT_ID = 'check.apps.googleusercontent.com';";
// A GIS stand-in whose token request succeeds at once.
const FAKE_GIS = `window.google = { accounts: { oauth2: { initTokenClient(o) { return {
  requestAccessToken() { setTimeout(() => o.callback({ access_token: 't', expires_in: 3600 }), 0); } }; } } } };`;
const CACHED_RAW = {
  courses: [{ id: 'c1', name: 'Art' }],
  courseWork: [{ id: 'k1', courseId: 'c1', title: 'Cached drawing', alternateLink: 'https://classroom.google.com/x',
    creationTime: new Date().toISOString(), dueDate: (() => {
      const d = new Date(); d.setDate(d.getDate() + 1);
      return { year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate() };
    })() }],
  announcements: [], materials: [],
};

async function livePage(browser, base, { gis, classroom, drive, cache }) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.route('**/config.js', (r) => r.fulfill({ status: 200, contentType: 'text/javascript', body: FAKE_CONFIG }));
  await page.route('https://accounts.google.com/**', (r) => (gis === 'fail'
    ? r.abort()
    : r.fulfill({ status: 200, contentType: 'text/javascript', body: FAKE_GIS })));
  await page.route('https://classroom.googleapis.com/**', (r) => (classroom === 'blocked'
    ? r.fulfill({ status: 403, contentType: 'application/json', body: '{"error":{"status":"PERMISSION_DENIED"}}' })
    : r.abort()));
  await page.route('https://www.googleapis.com/**', (r) => (drive === 'empty'
    ? r.fulfill({ status: 200, contentType: 'application/json', body: '{"files":[]}' })
    : r.abort()));
  if (cache !== undefined) {
    await page.addInitScript((c) => {
      if (!sessionStorage.getItem('seeded')) {
        localStorage.setItem('hc.classroom', c);
        sessionStorage.setItem('seeded', '1');
      }
    }, cache);
  }
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
  } catch (e) {
    check('run', false, e.message);
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
  console.log(failures.length ? `\n${failures.length} check(s) failed` : `\nall checks passed; screenshots in ${shotDir}`);
  process.exit(failures.length ? 1 : 0);
})();
