# Homework Calendar: design

Date: 2026-11-21
Status: waiting for approval

## Why

The user's little brother needs one place that shows what he has to do and when. Google Classroom has
his assignments, but it doesn't call out tests, it doesn't know about his after-school activities, and
it doesn't give him a simple "what's next" view. This app signs in to his Classroom, puts due dates and
tests on a calendar, lets him add his activities, and gives him a checklist to tick off.

**User:** the brother himself, on his own Google (school) account. He opens it on whatever device he
has (Chromebook, phone, computer).

## Goals

1. **Calendar** of his assignments (by due date), tests and quizzes, and his own activities.
2. **Tests stand out.** Anything in Classroom whose title or text contains "test" or "quiz" is marked
   as a test and highlighted.
3. **He can add his own items:** activities (for example soccer at 5pm, which can repeat weekly) and
   tests that a teacher only announced out loud.
4. **To-do checklist:** every assignment and test is a box he ticks when done. Overdue items that
   aren't ticked turn red. Ticked items get crossed off.
5. **"What's next" summary** at the top: tests coming up this week, what's due today and tomorrow,
   and what's overdue.
6. His ticks and activities are the same on every device he signs in on.

## Non-goals (v1)

- Reading the teacher's **weekly overview Google Doc.** We're waiting on a link to see how it's laid out.
  It may become phase 2: pulling test dates from the Doc automatically.
- Turning work in on Classroom. Google doesn't allow outside apps to do it for teacher-made
  assignments. Ticking a box in the app changes nothing in Classroom.
- Grades, teacher comments, attachments.
- Study plans for each test (checklist type B). Can come later.
- Notifications and reminders. A month view.
- More than one student.

## Anti-goals (failure even if it works)

- The app **writes to or changes anything in Classroom.** It is read-only.
- His data goes anywhere other than his browser and his own Google account. No server, no database,
  no analytics, no AI service.
- It's confusing for a kid. If he has to read instructions to use it, it failed.
- It costs money to run.

## Constraints

- **The school may block it.** School Google accounts are run by the school's admin, who can block
  outside apps from Classroom (and Drive). If that happens the sign-in fails with an
  "access blocked" or admin-policy error. The app must say that plainly ("Your school blocked this
  app. Ask a parent to contact the school's IT") instead of showing a broken page. There's no
  technical way around it. The fix is the school allowing it.
- **Google Cloud setup** is needed once, by the user (an older sibling or parent): a free project, the
  Classroom and Drive APIs turned on, an OAuth client for the page's web address, and the brother's
  email added as a test user. Because the app isn't verified by Google, he will see an
  "unverified app" warning the first time.
- Classroom has **no "test" type.** Tests arrive as assignments, quiz assignments, announcements or
  materials, and sometimes not at all.
- Classroom due dates are stored as a UTC date and time. They must be shown in his local time.

## Approaches considered

1. **Browser-only web page with Google sign-in (chosen).** A static page signs in with Google and calls
   the Classroom API directly from the browser. Ticks and activities save to a hidden app-data file in
   his Google Drive. Free, no server, works on any device. Cost: one-time Cloud setup and the
   unverified-app warning.
2. **Google Apps Script web app.** No Cloud setup, but schools often disable Apps Script for students,
   the page sits inside Google's frame with a warning banner, and it's harder to change later.
3. **Web app with its own server and database.** Most flexible, but needs a server kept running and
   maybe paid for. Far too much for one student's calendar.

The user picked **1**.

## Design

### Where it lives

A new folder `homework-calendar/` in this repo, separate from clipbot. Plain HTML, CSS and JavaScript
modules with no build step, so it can be hosted as static files (for example GitHub Pages) or opened
from `localhost` for testing.

### Sign-in and permissions

Google Identity Services token client in the browser. Read-only scopes plus his app folder:

- `classroom.courses.readonly`: his classes
- `classroom.coursework.me.readonly`: his assignments and whether he's turned them in
- `classroom.announcements.readonly`: announcements (to spot "test on Friday")
- `classroom.courseworkmaterials.readonly`: materials (some teachers post study guides there)
- `drive.appdata`: one hidden file in his Drive, only readable by this app

Tokens last about an hour. The app asks for a fresh one quietly when needed, and shows the sign-in
button again if that fails.

### Getting the data

On load and on a "Refresh" button:

1. List his active courses.
2. For each course: coursework (with his submission state), announcements and materials from roughly
   the last 30 days onward.
3. Build one list of **items**: `{id, source, course, title, link, dueAt?, kind: homework|test|activity,
   done}`.

**Test detection:** the title or text matches the whole words `test`, `quiz` or `exam`, ignoring case
(so "Unit 4 Quiz" matches but "contest" doesn't). Adding "exam" is my call.

**Tests with no date:** an announcement like "Test on Friday!" has no due date. Reading dates out of
free text is unreliable, so these show in "What's next" as **"Test mentioned in Math: add a date"**.
One tap lets him pick the date, which is saved.

**Auto-tick:** if Classroom shows an assignment as turned in or returned, it starts ticked. He can still
tick or untick anything by hand. His manual choice wins.

### Saved data

A single JSON file `homework-calendar.json` in his Drive app folder:

```json
{
  "version": 1,
  "checks": { "<itemId>": true },
  "testDates": { "<announcementId>": "2026-11-27" },
  "myItems": [
    { "id": "...", "kind": "activity", "title": "Soccer", "date": "2026-11-24",
      "time": "17:00", "repeatWeekly": true },
    { "id": "...", "kind": "test", "title": "Spelling test", "date": "2026-11-26" }
  ]
}
```

A copy is cached in the browser so the page shows instantly and still works briefly offline. Saving to
Drive happens a moment after each change. The newest change wins if two devices conflict.

### Screen (one page, phone-first)

```
 [Sign in with Google]          (before sign-in)

 My Homework               [↻ Refresh] [+ Add]
 ── What's next ──────────────────────────────
 ⚠ TEST Fri: Math Unit 4
 ⚠ Test mentioned in Science: add a date
 • Overdue: History map  (red)
 • Due today: Science worksheet
 • Due tomorrow: Reading log
 ── This week ◀ Nov 23–29 ▶ ──────────────────
 Mon  ☐ Reading log · Eng
 Tue  ⚽ Soccer 5:00pm
 Wed  ☑ ~~Science worksheet~~
 Fri  ☐ TEST Math Unit 4   (highlighted)
 ── Checklist ────────────────────────────────
 ☐ History map (overdue, red)
 ☐ Science worksheet · today
 ☐ TEST Math Unit 4 · Fri
```

- The week view is a list of days on a phone and a 7-column grid on wider screens.
- Each item links to its Classroom page.
- **+ Add** opens a short form: what (Activity / Test / Other homework), name, date, optional time,
  "every week" checkbox.
- Tapping one of his own items lets him edit or delete it.
- The checklist shows unticked items first (overdue, then by date) and ticked items from the last
  7 days, crossed off.

### Demo mode

A "Try with sample data" link shows the app with made-up classes and items, with no sign-in. It lets
the family see it before doing the Cloud setup, and it is what the tests use.

### Errors he might see

- School blocked the app: plain explanation (see Constraints).
- Not signed in or token expired: the sign-in button.
- Network down: the cached copy with "Showing saved info, can't reach Google right now".

### Setup guide

`homework-calendar/SETUP.md`: written for a non-programmer, step by step. Covers creating the Cloud
project, enabling the APIs, the consent screen (External, testing mode, add his email as test user),
the OAuth client with the page's address, pasting the client ID into `config.js`, and hosting it
(GitHub Pages or opening it locally).

### Testing

The logic (test detection, building items, overdue/today/tomorrow sorting, repeating activities, time
zones, merging saved ticks) lives in plain modules tested with Node's built-in test runner. The page
itself is checked in a headless browser using demo mode. The real Classroom connection can only be
tested on his account after setup.

## Left to the builder

- Exact styling, colors and fonts (bright and friendly, readable on a small phone).
- How far back to fetch, and paging details.
- Exactly how the week grid looks on wide screens.

## Open

- The weekly overview Doc (phase 2, after we see one).
- Hosting address, which the user decides during setup. The setup guide covers both GitHub Pages and
  running it locally.
