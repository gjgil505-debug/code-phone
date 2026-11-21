# Homework Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A static web page that reads a student's Google Classroom (read-only), shows assignments, tests and his own activities on a week calendar with a "What's next" summary and a to-do checklist, and syncs his ticks and activities through a hidden file in his Google Drive.

**Architecture:** Plain ES modules with no build step. Pure logic modules (`dates`, `items`, `summary`, `store`, `render`) are unit-tested with `node --test`. Thin browser modules (`google`, `persistence`, `app`) do sign-in, fetching, saving and DOM wiring. Demo mode (`?demo=1`) feeds sample data through the same pipeline and is what the browser check uses.

**Tech Stack:** HTML, CSS, JavaScript ES modules; Google Identity Services (token client); Classroom API v1; Drive API v3 (appDataFolder); Node 22 `node:test`; Playwright (pre-installed) for the demo-mode check.

**Spec:** `docs/superpowers/specs/2026-11-21-homework-calendar-design.md`

## Global Constraints

- Everything lives in `homework-calendar/`. Nothing in clipbot changes.
- No build step, no npm dependencies. `package.json` exists only for `"type": "module"` and `"test": "node --test tests/"`.
- Read-only Classroom. Scopes, exactly: `https://www.googleapis.com/auth/classroom.courses.readonly`, `https://www.googleapis.com/auth/classroom.coursework.me.readonly`, `https://www.googleapis.com/auth/classroom.announcements.readonly`, `https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly`, `https://www.googleapis.com/auth/drive.appdata`.
- No network calls except `accounts.google.com` (GIS script), `classroom.googleapis.com` and `www.googleapis.com` (Drive). No analytics, no AI service, no server.
- Test words: whole words `test`, `quiz`, `exam`, any case.
- Drive file name: `homework-calendar.json`, in `appDataFolder`. Saved state shape: `{version: 1, checks: {}, testDates: {}, myItems: [], updatedAt: <ms>}`.
- Week runs Monday–Sunday. All dates shown in the browser's local time zone.
- Kid-facing copy is short and plain. Blocked-by-school message, exactly: "Your school blocked this app from reading Google Classroom. Ask a parent to contact the school's IT." Offline message, exactly: "Showing saved info, can't reach Google right now."
- Every user-supplied or Classroom-supplied string is HTML-escaped before rendering.
- Every `localStorage` read/write is wrapped in try/catch; the page works without it.

## Review Focus

1. **Due time near midnight:** a teacher sets 11:59pm local; Classroom stores it as the next day in UTC. It must show on the correct local day (test in Task 1).
2. **Classroom text with `<`, `&` or quotes** (e.g. "Quiz: <b> vs <i>") must show as text, not break the page (test in Task 5).
3. **Saved file missing, empty or corrupt** (first run, or an older version) must load as an empty state, not crash (test in Task 4).
4. **Sign-in popup closed after Google's "Access blocked" page** must show the school-blocked hint, not a blank page (test in Task 6).
5. **A weekly activity that started mid-week** must not appear on days before its start date (test in Task 3).

---

## File map

```
homework-calendar/
  package.json          type: module, test script
  index.html            page shell, loads GIS script and src/app.js
  styles.css            phone-first styles
  config.js             export const CLIENT_ID = 'PASTE-YOUR-CLIENT-ID.apps.googleusercontent.com'
  SETUP.md              non-programmer setup + hosting guide
  src/dates.js          date helpers (pure)
  src/items.js          Classroom raw data + saved state -> items (pure)
  src/summary.js        what's next, checklist, week grid (pure)
  src/store.js          saved-state changes (pure)
  src/render.js         HTML strings (pure)
  src/demo.js           sample data relative to "now" (pure)
  src/google.js         GIS sign-in, Classroom fetch, Drive file, error classification
  src/persistence.js    localStorage cache + debounced Drive save
  src/app.js            DOM wiring
  tests/*.test.js       node:test unit tests
  scripts/demo-check.cjs  Playwright check of demo mode
```

## Shared types (JSDoc in `src/items.js`)

```js
/** @typedef {{courses: {id:string,name:string}[],
 *   courseWork: {id,courseId,title,description?,alternateLink,dueDate?,dueTime?,creationTime,submissionState?}[],
 *   announcements: {id,courseId,text,alternateLink,creationTime}[],
 *   materials: {id,courseId,title,description?,alternateLink,creationTime}[]}} RawData */
/** @typedef {{id:string, source:'coursework'|'announcement'|'material'|'mine',
 *   courseName:string, title:string, link:string|null, dueAt:Date|null, allDay:boolean,
 *   kind:'homework'|'test'|'activity', done:boolean, needsDate:boolean,
 *   repeatWeekly:boolean, time:string|null}} Item */
/** @typedef {{version:1, checks:Object<string,boolean>, testDates:Object<string,string>,
 *   myItems:{id,kind,title,date,time?,repeatWeekly?}[], updatedAt:number}} SavedState */
```

Item ids: `cw:<id>`, `an:<id>`, `mt:<id>`, `my:<id>`.

---

### Task 1: Scaffold and date helpers

**Files:**
- Create: `homework-calendar/package.json`, `homework-calendar/src/dates.js`
- Test: `homework-calendar/tests/dates.test.js`

**Interfaces:**
- Produces: `classroomDueToDate(dueDate, dueTime) -> {date: Date, allDay: boolean} | null`, `ymd(date) -> 'YYYY-MM-DD'` (local), `parseYmd(str) -> Date` (local midnight), `startOfDay(date) -> Date`, `addDays(date, n) -> Date`, `startOfWeek(date) -> Date` (local Monday 00:00), `sameDay(a, b) -> boolean`.

- [ ] **Step 1: Write failing tests.** Run tests with `TZ=America/Los_Angeles` set in the npm script for this file's cases (set `process.env.TZ` is not reliable after start, so the `test` script is `TZ=America/Los_Angeles node --test tests/`).

```js
test('UTC due time maps to the local day', () => {
  // 11:59pm Pacific on Nov 24 is stored as Nov 25 07:59 UTC
  const r = classroomDueToDate({year:2026,month:11,day:25},{hours:7,minutes:59});
  assert.equal(ymd(r.date), '2026-11-24'); assert.equal(r.allDay, false);
});
test('missing dueTime is all-day on that date', () => {
  const r = classroomDueToDate({year:2026,month:11,day:25}, undefined);
  assert.equal(ymd(r.date), '2026-11-25'); assert.equal(r.allDay, true);
});
test('no dueDate returns null', () => assert.equal(classroomDueToDate(undefined, undefined), null));
test('startOfWeek is Monday', () => {
  assert.equal(ymd(startOfWeek(parseYmd('2026-11-29'))), '2026-11-23'); // Sunday -> Monday before
  assert.equal(ymd(startOfWeek(parseYmd('2026-11-23'))), '2026-11-23');
});
test('addDays crosses month end', () => assert.equal(ymd(addDays(parseYmd('2026-11-30'), 1)), '2026-12-01'));
```

- [ ] **Step 2:** Run `cd homework-calendar && npm test` — expect FAIL (module not found).
- [ ] **Step 3:** Create `package.json` (`{"name":"homework-calendar","private":true,"type":"module","scripts":{"test":"TZ=America/Los_Angeles node --test tests/"}}`) and implement `src/dates.js`. Classroom `dueTime` hours/minutes may be absent individually; treat a missing field as 0. A `dueTime` that is `{}` counts as present (midnight UTC).
- [ ] **Step 4:** Run `npm test` — expect PASS.
- [ ] **Step 5:** Commit `feat(homework): scaffold and date helpers`.

### Task 2: Build items from Classroom data

**Files:**
- Create: `homework-calendar/src/items.js`
- Test: `homework-calendar/tests/items.test.js`

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces: `isTestText(...strings) -> boolean`; `buildItems(raw: RawData, saved: SavedState, now: Date) -> Item[]`.

Rules (from the spec):
- Every courseWork becomes an item; `kind` is `test` if `isTestText(title, description)`, else `homework`. Keep it only if `dueAt >= now - 30 days`, or it has no due date and `creationTime >= now - 30 days`.
- Announcements and materials become items **only** if they match test words; `kind: 'test'`, `dueAt: null`, created within the last 30 days. Announcement title is the first line of `text`, cut to 80 characters.
- `saved.testDates[id]` (a `YYYY-MM-DD`) sets `dueAt` to that local midnight and `allDay: true`.
- `needsDate = kind === 'test' && dueAt === null`.
- `done = saved.checks[id]` if it's a boolean, else `submissionState` is `TURNED_IN` or `RETURNED`.
- `saved.myItems` become items with `source: 'mine'`, `dueAt` from `date` + optional `time` (`HH:MM`, local), `allDay` when no time, `repeatWeekly` copied, `link: null`, `courseName: ''`.
- `courseName` from `raw.courses`; unknown course → `''`.

- [ ] **Step 1: Write failing tests.**

```js
test('test words match whole words only', () => {
  assert.ok(isTestText('Unit 4 Quiz')); assert.ok(isTestText('', 'TEST on friday'));
  assert.ok(isTestText('Final Exam')); assert.ok(!isTestText('Science contest'));
  assert.ok(!isTestText('Testing the volcano'));
});
test('coursework due date, kind, and turned-in auto-tick', () => { /* one homework TURNED_IN -> done true; one "Quiz" -> kind test */ });
test('manual check overrides submission state', () => { /* TURNED_IN with checks[id]=false -> done false */ });
test('announcement without test words is dropped; with them needsDate', () => {
  // "Field trip Friday" dropped; "Test on Friday!" -> kind test, needsDate true, dueAt null, title 'Test on Friday!'
});
test('testDates gives an undated test a date', () => { /* testDates['an:a1']='2026-11-27' -> ymd(dueAt)=='2026-11-27', needsDate false */ });
test('old coursework is dropped', () => { /* due 45 days before now -> absent */ });
test('my items become items', () => {
  // {id:'x',kind:'activity',title:'Soccer',date:'2026-11-24',time:'17:00',repeatWeekly:true}
  // -> id 'my:x', source 'mine', allDay false, dueAt local 17:00, repeatWeekly true
});
```

Each test builds a small `RawData` inline with `now = new Date(2026, 10, 23, 15, 0)` (Mon Nov 23, 3pm local) and asserts the fields named in the comment.

- [ ] **Step 2:** Run `npm test` — expect FAIL.
- [ ] **Step 3:** Implement `src/items.js`. `isTestText` uses `/\b(test|quiz|exam)\b/i` on each string; `\b` treats "testing" as not matching because the word continues.
- [ ] **Step 4:** Run `npm test` — expect PASS.
- [ ] **Step 5:** Commit `feat(homework): build items from classroom data`.

### Task 3: What's next, checklist, week grid

**Files:**
- Create: `homework-calendar/src/summary.js`
- Test: `homework-calendar/tests/summary.test.js`

**Interfaces:**
- Consumes: `Item` from Task 2; Task 1 helpers.
- Produces:
  - `isOverdue(item, now) -> boolean`: not done, not activity, has `dueAt`; all-day → its date is before today; timed → `dueAt < now`.
  - `whatsNext(items, now) -> {tests: Item[], needsDate: Item[], overdue: Item[], today: Item[], tomorrow: Item[]}`. `tests`: undone tests with `dueAt` from today through today+6, by date. `needsDate`: undone `needsDate` items. `overdue`: overdue **homework** only. `today`/`tomorrow`: undone homework on that local day that isn't overdue. Activities never appear here.
  - `checklist(items, now) -> {item: Item, status: 'overdue'|'open'|'done'}[]`. Non-activity items only. Order: overdue (oldest first), open with a date (soonest first), open without a date, then done items whose `dueAt` is within the last 7 days or later (soonest first). Done items with no date are left out.
  - `weekDays(items, weekStart) -> {date: Date, items: Item[]}[]` of length 7. An item appears on the day of its `dueAt`. A `repeatWeekly` item appears on every day in the week with the same weekday on or after its start date. Within a day: timed items by time, then all-day items.

- [ ] **Step 1: Write failing tests** (with `now = new Date(2026, 10, 23, 15, 0)`, Monday):

```js
test('timed homework earlier today is overdue; all-day today is not', ...);
test('whatsNext groups tests this week, overdue, today, tomorrow; skips activities and done', ...);
test('test 8 days out is not in tests this week', ...);
test('checklist order: overdue, open dated, open undated, done recent', ...);
test('done item from 10 days ago is left out of the checklist', ...);
test('weekly activity repeats on its weekday, not before its start date', () => {
  // Soccer starting Wed 2026-11-25, repeatWeekly -> week of Nov 23: only Wed; week of Nov 30: Wed Dec 2
});
test('weekDays sorts timed before all-day', ...);
```

Each test asserts the exact ids in the returned arrays, in order.

- [ ] **Step 2:** Run `npm test` — expect FAIL.
- [ ] **Step 3:** Implement `src/summary.js`.
- [ ] **Step 4:** Run `npm test` — expect PASS.
- [ ] **Step 5:** Commit `feat(homework): summary, checklist and week grid`.

### Task 4: Saved state

**Files:**
- Create: `homework-calendar/src/store.js`
- Test: `homework-calendar/tests/store.test.js`

**Interfaces:**
- Produces (all pure, return a new state with `updatedAt` set to the passed `now` ms):
  - `emptyState() -> SavedState` (`updatedAt: 0`)
  - `normalizeState(raw: unknown) -> SavedState`: accepts an object or a JSON string; anything unparseable, non-object, or with wrong-typed fields becomes the matching empty field; drops `myItems` entries without `id`, `title` and a valid `date`.
  - `setCheck(state, id, done, now)`, `setTestDate(state, id, ymd, now)`
  - `addMyItem(state, {kind, title, date, time?, repeatWeekly?}, now, makeId = () => crypto.randomUUID())`
  - `updateMyItem(state, id, fields, now)`, `deleteMyItem(state, id, now)` (also removes `checks['my:'+id]`)
  - `pickNewer(a, b) -> SavedState` by `updatedAt` (ties → `a`).

- [ ] **Step 1: Write failing tests.**

```js
test('normalizeState handles null, "", "{bad", [], and {checks: 5}', () => {
  for (const x of [null, '', '{bad', [], {checks: 5}]) assert.deepEqual(normalizeState(x), emptyState());
});
test('normalizeState drops broken myItems and keeps good ones', ...);
test('setCheck does not mutate and bumps updatedAt', ...);
test('addMyItem trims title and uses makeId', () => { /* '  Soccer ' -> 'Soccer', id from makeId */ });
test('deleteMyItem removes its check', ...);
test('pickNewer prefers later updatedAt', ...);
```

- [ ] **Step 2:** Run `npm test` — expect FAIL.
- [ ] **Step 3:** Implement `src/store.js`. `addMyItem` with an empty trimmed title throws `Error('Name is required')`; the form shows that.
- [ ] **Step 4:** Run `npm test` — expect PASS.
- [ ] **Step 5:** Commit `feat(homework): saved state`.

### Task 5: Rendering and demo data

**Files:**
- Create: `homework-calendar/src/render.js`, `homework-calendar/src/demo.js`
- Test: `homework-calendar/tests/render.test.js`, `homework-calendar/tests/demo.test.js`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `escapeHtml(s) -> string` (`& < > " '`).
  - `renderWhatsNext(summary, now) -> string`. Each test line starts with `⚠ TEST`; needs-date lines read `Test mentioned in <course>: add a date` and carry a `data-action="set-date" data-id="<id>"` button. Empty summary → `Nothing due. Nice!`.
  - `renderWeek(days, now) -> string`. Day header shows short weekday and date; today gets class `today`. Each item has class `item kind-<kind>` plus `done` when done and `overdue` when overdue; tests show the `TEST` label; activities show their time like `5:00pm`. Classroom items link to `link` with `target="_blank" rel="noopener"`. Mine items carry `data-action="edit" data-id`.
  - `renderChecklist(rows) -> string`. Each row is `<label class="row <status>"><input type="checkbox" data-action="check" data-id="…" [checked]> …</label>` with the course name and a due label (`today`, `tomorrow`, weekday name within 6 days, else `Nov 30`; undated → `no date`).
  - `demoData(now) -> {raw: RawData, saved: SavedState}`: 3 classes (Math, Science, English), at least: one overdue homework, one due today, one due tomorrow, one turned in, a dated "Unit 4 Quiz" this week, an announcement "Test on Friday!" with no date, a weekly "Soccer" activity at 17:00, and a title containing `<` and `&`. All dates relative to `now`.

- [ ] **Step 1: Write failing tests.**

```js
test('escapeHtml', () => assert.equal(escapeHtml(`<a href="x">&'`), '&lt;a href=&quot;x&quot;&gt;&amp;&#39;'));
test('Classroom titles are escaped in every renderer', () => {
  // item title 'Quiz: <b> & <i>' -> output contains 'Quiz: &lt;b&gt; &amp; &lt;i&gt;' and no '<b>'
});
test('overdue and done classes', ...);
test('needs-date line has set-date button', ...);
test('empty summary says Nothing due. Nice!', ...);
test('demoData runs through buildItems/whatsNext with something in every group', () => {
  // whatsNext(buildItems(raw, saved, now), now): tests, needsDate, overdue, today, tomorrow all non-empty
});
```

- [ ] **Step 2:** Run `npm test` — expect FAIL.
- [ ] **Step 3:** Implement both modules.
- [ ] **Step 4:** Run `npm test` — expect PASS.
- [ ] **Step 5:** Commit `feat(homework): rendering and demo data`.

### Task 6: Google sign-in, Classroom fetch, Drive file

**Files:**
- Create: `homework-calendar/src/google.js`
- Test: `homework-calendar/tests/google.test.js`

**Interfaces:**
- Produces:
  - `SCOPES` (the five scopes in Global Constraints, space-joined).
  - `classifyGoogleError({status?, body?, gisError?, networkError?}) -> 'blocked'|'signin'|'network'|'other'`. `networkError` → `network`. `status === 401` → `signin`. `status === 403` with body text containing `ClassroomApiDisabled`, `admin_policy_enforced`, `PERMISSION_DENIED` or `has not been granted` → `blocked`. `gisError` of `popup_closed`, `access_denied` or `popup_failed_to_open` → `signin`. Else `other`.
  - `createAuth(clientId, google = window.google) -> {signIn(): Promise<string>, getToken(): Promise<string>}`. Uses `google.accounts.oauth2.initTokenClient`. `signIn` uses `prompt: 'consent'` the first time and `''` after; `getToken` returns the cached token if more than 60s remain, else requests one with `prompt: ''`. Rejects with an `Error` whose `.kind` comes from `classifyGoogleError`.
  - `createApi(getToken, fetchFn = fetch) -> {fetchClassroom(now): Promise<RawData>, loadSaved(): Promise<SavedState|null>, saveSaved(state): Promise<void>}`. Every request sends `Authorization: Bearer <token>`; non-2xx throws `Error` with `.kind`, `.status`; a rejected fetch throws `.kind = 'network'`.
    - Courses: `GET https://classroom.googleapis.com/v1/courses?studentId=me&courseStates=ACTIVE&pageSize=100`.
    - Per course, in parallel: `courses/{id}/courseWork?courseWorkStates=PUBLISHED&pageSize=100`, `courses/{id}/courseWork/-/studentSubmissions?userId=me&pageSize=100` (map `courseWorkId -> state` onto `submissionState`), `courses/{id}/announcements?announcementStates=PUBLISHED&pageSize=50`, `courses/{id}/courseWorkMaterials?courseWorkMaterialStates=PUBLISHED&pageSize=50`. Follow `nextPageToken` up to 3 pages each. A 403/404 on announcements or materials for one course is skipped (that course has them turned off); any other failure throws.
    - Drive find: `GET https://www.googleapis.com/drive/v3/files?spaces=appDataFolder&q=name%3D'homework-calendar.json'&fields=files(id)`. Read: `GET …/files/{id}?alt=media` → `normalizeState`. No file → `null`.
    - Drive save: create with `POST https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart` (metadata `{name, parents:['appDataFolder']}`), else `PATCH https://www.googleapis.com/upload/drive/v3/files/{id}?uploadType=media`. Remember the file id after the first find or create.

- [ ] **Step 1: Write failing tests** with a fake `fetchFn` that records URLs and returns canned JSON:

```js
test('classifyGoogleError cases', () => {
  assert.equal(classifyGoogleError({status:403, body:'{"error":{"status":"PERMISSION_DENIED","message":"@ClassroomApiDisabled"}}'}), 'blocked');
  assert.equal(classifyGoogleError({status:401}), 'signin');
  assert.equal(classifyGoogleError({gisError:'popup_closed'}), 'signin');
  assert.equal(classifyGoogleError({networkError:true}), 'network');
  assert.equal(classifyGoogleError({status:500}), 'other');
});
test('fetchClassroom merges submission states and follows one nextPageToken', ...);
test('fetchClassroom skips a 404 on materials for one course', ...);
test('loadSaved returns null when no file; saveSaved creates then patches', ...);
test('403 on courses throws kind blocked', ...);
```

- [ ] **Step 2:** Run `npm test` — expect FAIL.
- [ ] **Step 3:** Implement `src/google.js`. `createAuth` is not unit-tested (needs the real GIS); keep it under 40 lines.
- [ ] **Step 4:** Run `npm test` — expect PASS.
- [ ] **Step 5:** Commit `feat(homework): google sign-in, classroom and drive`.

### Task 7: Persistence

**Files:**
- Create: `homework-calendar/src/persistence.js`
- Test: `homework-calendar/tests/persistence.test.js`

**Interfaces:**
- Consumes: `normalizeState`, `pickNewer`, `emptyState` (Task 4); `api.loadSaved/saveSaved` (Task 6).
- Produces: `createPersistence({storage, api, debounceMs = 1500, setTimer = setTimeout, clearTimer = clearTimeout}) -> {readCache(): SavedState, readCacheRaw(key): any, writeCache(key, value), load(): Promise<SavedState>, save(state): void, flush(): Promise<void>}`.
  - Cache keys: `hc.state` (SavedState JSON) and `hc.classroom` (last `RawData` JSON with dates as strings).
  - `load()`: cached state, then `pickNewer(cached, remote ?? emptyState())`; on Drive failure returns cached state.
  - `save(state)`: writes cache now, saves to Drive after `debounceMs` (later calls replace the pending one). A failed Drive save keeps the cache and retries on the next `save` or `flush`.
  - A `storage` that throws on every call must not break anything.

- [ ] **Step 1: Write failing tests** with fake storage, fake api and a manual timer:

```js
test('throwing storage is survived', ...);
test('load prefers the newer of cache and Drive', ...);
test('load falls back to cache when Drive fails', ...);
test('save debounces to one Drive call', ...);
test('failed Drive save retries on flush', ...);
```

- [ ] **Step 2:** Run `npm test` — expect FAIL.
- [ ] **Step 3:** Implement `src/persistence.js`.
- [ ] **Step 4:** Run `npm test` — expect PASS.
- [ ] **Step 5:** Commit `feat(homework): cache and drive sync`.

### Task 8: The page

**Files:**
- Create: `homework-calendar/index.html`, `homework-calendar/styles.css`, `homework-calendar/config.js`, `homework-calendar/src/app.js`, `homework-calendar/scripts/demo-check.cjs`

**Interfaces:**
- Consumes: everything above.

Behavior:
- `index.html`: header "My Homework" with Refresh and + Add buttons; sections `#next`, `#week` (with ◀ / ▶ and the range label `Nov 23–29`), `#checklist`; a `#status` line for errors/offline; a `<dialog id="add">` form (What: Activity / Test / Other homework; Name; Date; Time (optional); Every week checkbox, shown for activities only; Save, Delete (edit only), Cancel); a `<dialog id="pick-date">` with one date input. Loads `https://accounts.google.com/gsi/client` async and `src/app.js` as a module.
- Signed-out screen: one big "Sign in with Google" button and a "Try with sample data" link (`?demo=1`).
- `app.js` flow: demo mode uses `demoData(new Date())` and keeps state in memory only. Otherwise, if `CLIENT_ID` still starts with `PASTE`, show "This app isn't set up yet. See SETUP.md." On sign-in: show cached Classroom data at once if present, then fetch fresh, `buildItems`, render all three sections. Every check, add, edit, delete or date pick goes through `store.js`, then `persistence.save`, then re-render. Refresh re-fetches. On `blocked` show the exact blocked message; on `network` show the exact offline message with cached data; on `signin` show the sign-in button again, plus under it: "If Google said 'Access blocked', your school blocked this app. Ask a parent to contact the school's IT."
- `styles.css`: phone-first; week is a stacked list of days under 700px wide and a 7-column grid above; tests get a bold warm highlight; overdue rows red; done rows struck through and dimmed; tap targets at least 44px; light and dark via `prefers-color-scheme`.
- `scripts/demo-check.cjs`: starts `python3 -m http.server` on a free port in `homework-calendar/`, opens `/?demo=1` in Playwright Chromium at 390×844 and at 1280×800, and asserts: `#next` contains `⚠ TEST` and `add a date`; a `.row.overdue` exists; ticking the first checklist box gives that row class `done`; adding activity "Piano" today at 16:00 through the dialog shows "Piano" in `#week`; the "Test on Friday!" title (escaped demo title too) is visible; no console errors; no horizontal scroll at 390px (`scrollWidth <= clientWidth`). Saves screenshots to the path given in `argv[2]`. Exits non-zero on any failure.

- [ ] **Step 1:** Write `scripts/demo-check.cjs` first. Run `node scripts/demo-check.cjs <scratchpad>/shots` — expect FAIL (no page).
- [ ] **Step 2:** Write `config.js`, `index.html`, `styles.css`, `src/app.js`.
- [ ] **Step 3:** Run `node scripts/demo-check.cjs <scratchpad>/shots` — expect PASS; look at both screenshots.
- [ ] **Step 4:** Run `npm test` — expect PASS.
- [ ] **Step 5:** Commit `feat(homework): the page`.

### Task 9: Setup guide

**Files:**
- Create: `homework-calendar/SETUP.md`
- Modify: `README.md` (one line at the top pointing to `homework-calendar/`)

Content, written for a non-programmer, numbered steps:
1. See it first: how to open demo mode.
2. Google Cloud: create a project; enable **Google Classroom API** and **Google Drive API**; OAuth consent screen → External, app name "Homework Calendar", testing mode, add the brother's email under Test users, add the five scopes; Credentials → OAuth client ID → Web application → Authorized JavaScript origins = the page's address (e.g. `https://<user>.github.io` and `http://localhost:8000`).
3. Paste the client ID into `config.js`.
4. Host it: GitHub Pages (Settings → Pages → deploy from branch; the app is at `https://<user>.github.io/code-phone/homework-calendar/`), or locally with `python3 -m http.server 8000` in the folder.
5. First sign-in: the "Google hasn't verified this app" screen → Advanced → Continue; tick all permission boxes.
6. If it says the school blocked it: what that means, what to ask the school IT for (allow the app's OAuth client ID for Classroom), and the fallback of sending the weekly overview Doc instead.

- [ ] **Step 1:** Write `SETUP.md` and the README line.
- [ ] **Step 2:** Check every step against the current Google Cloud console wording (look it up; do not guess menu names) and that the scopes listed match `SCOPES` in `src/google.js` exactly.
- [ ] **Step 3:** Commit `docs(homework): setup guide`.
