// Browser check of demo mode. Usage: node scripts/demo-check.cjs <screenshot-dir>
// Serves homework-calendar/ with python3, opens /?demo=1 in Chromium at phone and desktop sizes.
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
  } catch (e) {
    check('run', false, e.message);
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
  console.log(failures.length ? `\n${failures.length} check(s) failed` : `\nall checks passed; screenshots in ${shotDir}`);
  process.exit(failures.length ? 1 : 0);
})();
