# GTA 6 Hype Clip Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An unattended bot that detects hype moments in the top GTA 6 Twitch streams, renders the best one every 10 minutes into a hooked 9:16 short with captions and the streamer's tag, and auto-posts the best videos to YouTube Shorts, TikTok and Instagram Reels within per-platform daily budgets.

**Architecture:** A single asyncio process (`clipbot run`) with four loops:
- discovery (every 5 min)
- chat listener and hype detector, with clip creation on spike
- render scheduler (every 10 min)
- publisher (every 1 min)

They share state through SQLite. Rendering is ffmpeg + faster-whisper, run in a worker thread. Each platform publisher is a plug-in behind one interface.

**Tech Stack:** Python ≥3.11, httpx, websockets, PyYAML, python-dotenv, faster-whisper, yt-dlp, ffmpeg/ffprobe (system), SQLite (stdlib), pytest, pytest-asyncio, respx.

**Spec:** `docs/superpowers/specs/2026-11-21-gta6-clip-bot-design.md`

## Global Constraints

- Python ≥3.11. Package name `clipbot`. Console script `clipbot`.
- No paid services. No AI APIs. Hook text is template-only.
- Output: 1080×1920, H.264 + AAC, audio normalised to −14 LUFS.
- Defaults:
  - `top_n: 25`
  - `game_name: "Grand Theft Auto VI"`
  - `render_interval_min: 10`
  - `discovery_interval_min: 5`
  - `hype_threshold: 3.0`
  - `min_post_score: 3.5`
  - `channel_cooldown_s: 120`
  - `max_clips_per_hour: 40`
  - `bucket_s: 5`
  - `baseline_window_s: 300`
  - `trigger_buckets: 2`
  - `freshness_hours: 6`
  - `keep_days: 7`
  - budgets: YouTube 6, TikTok 10, Instagram 20
  - `quiet_hours: null` (example `"03:00-08:00"`)
- Streamer tag `@<DisplayName>`:
  - bottom centre for the whole video
  - bold white, dark outline, semi-transparent pill
  - bottom edge ≥ 220 px from the frame bottom (platform safe area)
  - captions sit directly above it
- Hook:
  - cold open is the loudest 1.5 s window, then the full clip
  - hook text shown for the first 3.0 s at the top
  - no template repeated within the last 10 videos
- No emoji in rendered text.
- Twitch calls are mocked in tests. Nothing in tests touches the network.
- Secrets only in `.env`; tokens persisted in `data/tokens.json` (gitignored).

## Review Focus

1. **Streamer offline or clipping disabled mid-run** (Create Clip returns 403/404 or the clip never appears): the moment is marked `unusable` and nothing crashes. Test in Task 4.
2. **Silent or very short clip** (no audio track, or a clip under 3 s): the peak falls back to the last third; the render still succeeds or is cleanly skipped. Tests in Tasks 5–6.
3. **Transcript is empty** (no speech): the video renders with no captions; the safety check passes. Test in Task 6.
4. **A platform's token is revoked**: that platform is disabled in state and logged; the other platforms keep posting. Test in Task 8.
5. **Process restarts mid-day**: the daily post counts and the "already posted" set come from SQLite, so it never double-posts or exceeds a budget after a restart. Test in Task 7.

---

## File Structure

```
pyproject.toml, .gitignore, .env.example, config.example.yaml, README.md
clipbot/
  config.py          Settings dataclasses + load_settings()
  db.py              SQLite schema + typed accessors
  hype.py            ChatMessage, HypeDetector, Trigger
  twitch/chat.py     IRC line parser + ChatListener (websocket)
  twitch/api.py      Helix client: tokens, discovery, clips
  clipper.py         Trigger -> clip -> Moment row
  scheduler.py       pick_winner()
  render/peak.py     find_peak()
  render/hooks.py    HookPicker
  render/captions.py transcribe() + build_ass()
  render/compose.py  build_ffmpeg_cmd()
  render/pipeline.py render_moment()
  safety.py          is_safe()
  publish/base.py    Publisher protocol, PostResult, AuthError
  publish/planner.py due_platforms(), choose_video()
  publish/youtube.py, tiktok.py, instagram.py
  oauth.py           local-redirect OAuth helper + TokenStore
  housekeeping.py    cleanup()
  app.py             run loops
  cli.py             run | auth | render | status
deploy/clipbot.service, Dockerfile
tests/ (mirrors the modules above; fixtures in tests/fixtures/)
```

---

### Task 1: Scaffold, config, database

**Files:**
- Create:
  - `pyproject.toml`, `.gitignore`, `.env.example`, `config.example.yaml`
  - `clipbot/__init__.py`, `clipbot/config.py`, `clipbot/db.py`
- Test: `tests/test_config.py`, `tests/test_db.py`

**Interfaces:**
- Produces:
  - `load_settings(config_path: Path | None, env: Mapping[str,str]) -> Settings`.
    `Settings` is a frozen dataclass with every Global Constraints default, plus:
    - `budgets: dict[str,int]`
    - `enabled: dict[str,bool]` (all False by default)
    - `facecams: dict[str, tuple[int,int,int,int]]` (login → x,y,w,h in source px)
    - `emotes: dict[str, list[str]]` (keys `funny`, `hype`, `shock`)
    - `blocklist: list[str]`, `channel_blocklist: list[str]`
    - `data_dir: Path` (default `data`), `output_dir: Path` (default `output`)
    - `twitch_client_id`, `twitch_client_secret` (from env)
  - `Db(path: Path)` with these methods:
    - `add_moment(m: Moment) -> int`
    - `set_moment_status(id, status)`
    - `ready_moments(since: datetime) -> list[Moment]`
    - `add_video(v: Video) -> int`
    - `videos_since(since) -> list[Video]`
    - `add_post(p: Post)`
    - `posts_since(platform, since) -> list[Post]`
    - `posted_video_ids(platform) -> set[int]`
    - `get_state(key) -> str|None`, `set_state(key, value)`
    - `recent_hook_ids(n: int) -> list[str]`
  - `Moment` dataclass fields:
    - `id`, `channel`, `display_name`, `trigger_type`, `score: float`
    - `created_at: datetime`, `clip_id`, `clip_url`
    - `status` (`pending|ready|unusable|rendered|skipped`), `chat_snippet`
  - `Video` dataclass fields: `id`, `moment_id`, `path`, `meta_path`, `score`,
    `hook_id`, `safe: bool`, `created_at`
  - `Post` dataclass fields: `platform`, `video_id`, `remote_id`, `url`,
    `status` (`ok|failed`), `created_at`, `error`
  - All datetimes are timezone-aware UTC.

- [ ] **Step 1: Write failing tests.**
  - `test_defaults_match_spec`: `load_settings(None, {})` has:
    - `top_n == 25`, `render_interval_min == 10`, `hype_threshold == 3.0`
    - `budgets == {"youtube":6,"tiktok":10,"instagram":20}`
    - `all(not v for v in enabled.values())`
  - `test_yaml_overrides`: YAML `top_n: 5` and `enabled: {youtube: true}` give
    `top_n == 5` and `enabled["youtube"]`.
  - `test_env_secrets`: env `TWITCH_CLIENT_ID=x` gives `twitch_client_id == "x"`.
  - `test_moment_roundtrip`: add a ready moment, then `ready_moments(since)` returns
    it with equal fields.
  - `test_posts_since_filters_platform_and_time`.
  - `test_state_kv`.
- [ ] **Step 2:** Run `pytest tests/test_config.py tests/test_db.py -v`. Expected: FAIL (import errors).
- [ ] **Step 3: Implement.**
  - `pyproject.toml`: deps from the Tech Stack, `[project.scripts] clipbot = "clipbot.cli:main"`,
    pytest `asyncio_mode = "auto"`.
  - `.gitignore`: `data/`, `output/`, `.env`, `__pycache__/`.
  - `config.example.yaml`: lists every setting with comments.
  - `db.py`: uses `sqlite3` with `CREATE TABLE IF NOT EXISTS` for `moments`, `videos`,
    `posts`, `state`, and stores datetimes as ISO strings.
- [ ] **Step 4:** Run the same tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: scaffold, settings and sqlite store`.

### Task 2: Chat parsing and hype detector

**Files:**
- Create: `clipbot/hype.py`, `clipbot/twitch/__init__.py`, `clipbot/twitch/chat.py`
- Test: `tests/test_hype.py`, `tests/test_chat.py`

**Interfaces:**
- Consumes: `Settings` (Task 1).
- Produces:
  - `ChatMessage(channel: str, user: str, text: str, ts: float)`.
  - `parse_irc_line(line: str) -> ChatMessage | None`: handles `PRIVMSG` with or
    without IRCv3 tags; returns None for PING and other commands.
  - `HypeDetector(settings)` with:
    - `.feed(msg: ChatMessage) -> Trigger | None`
    - `.tick(now: float) -> list[Trigger]`
  - `Trigger(channel: str, score: float, trigger_type: Literal["funny","hype","shock","general"], ts: float, snippet: list[str])`.
  - `ChatListener(channels_provider: Callable[[], set[str]], on_message: Callable[[ChatMessage], None])`
    with `async run()`:
    - connects to `wss://irc-ws.chat.twitch.tv:443` as `justinfan<rand>`
    - JOINs/PARTs channels to match `channels_provider()` every 30 s
    - answers PING
    - reconnects with backoff 1→60 s

**Hype algorithm:**
- Messages fall into `bucket_s` buckets per channel.
- When a bucket closes, compute
  `raw = count / max(baseline, 1.0)`
  and
  `score = raw * (1 + 0.5*emote_share) * (0.5 + 0.5*unique_share)`, where:
  - `emote_share` = share of messages containing any configured emote or word
  - `unique_share` = unique users ÷ count
- Update the baseline as an EMA with `alpha = bucket_s / baseline_window_s`.
- There's no trigger until a channel has `baseline_window_s` of history (warm-up).
- Trigger when `trigger_buckets` consecutive buckets have `score ≥ hype_threshold`.
  The reported score is the max over those buckets.
- After a trigger, the channel is on cooldown for `channel_cooldown_s`.
- `trigger_type` is the emote category with the most hits in the triggering buckets.
  It's `general` if there were no hits.
- `snippet` is the last 8 message texts.

- [ ] **Step 1: Write failing tests.** Use synthetic messages with explicit `ts`.
  - `test_parse_privmsg_with_tags` gives `ChatMessage("xqc","bob","KEKW",...)`.
  - `test_parse_ping_returns_none`.
  - `test_no_trigger_during_warmup`.
  - `test_steady_chat_never_triggers`: 2 msg/s for 20 min gives zero triggers.
  - `test_spike_triggers_funny`: after 6 min at 2 msg/s, 12 s at 30 msg/s with
    `KEKW` from distinct users gives exactly one Trigger with `trigger_type=="funny"`
    and `score >= 3.0`.
  - `test_single_bucket_spike_does_not_trigger`: one 5 s burst only.
  - `test_cooldown_suppresses_second_spike_within_120s`.
  - `test_small_and_big_channel_scored_relative_to_own_baseline`: a channel going
    0.2 → 2 msg/s triggers; a channel going 40 → 45 msg/s doesn't.
- [ ] **Step 2:** Run `pytest tests/test_hype.py tests/test_chat.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `parse_irc_line`, `HypeDetector`, and `ChatListener`
  (`ChatListener` has no unit test beyond the parser; it's covered by Task 9 manual
  smoke).
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: twitch chat parsing and hype detection`.

### Task 3: Twitch Helix client

**Files:**
- Create: `clipbot/oauth.py` (the `TokenStore` part only), `clipbot/twitch/api.py`
- Test: `tests/test_twitch_api.py` (respx)

**Interfaces:**
- Consumes: `Settings`.
- Produces:
  - `TokenStore(path: Path)` with:
    - `.get(name) -> dict | None`
    - `.put(name, token: dict)`

    It writes JSON atomically (temp file + rename).
  - `TwitchApi(settings, tokens: TokenStore, client: httpx.AsyncClient)` with:
    - `async top_streams() -> list[StreamInfo]`: resolves the game id by `game_name`
      via `GET /helix/games` (cached), then `GET /helix/streams?game_id=&first=100`.
      It sorts by `viewer_count` descending, drops `channel_blocklist`, and keeps
      the top `top_n`.
    - `async create_clip(broadcaster_id) -> str | None`: returns the clip id.
      On 403/404 it returns None.
    - `async wait_clip(clip_id, timeout_s=20) -> ClipInfo | None`: polls
      `GET /helix/clips?id=` every 2 s.
  - `StreamInfo(user_id, login, display_name, viewers)`.
  - `ClipInfo(id, url, duration)`.
  - Tokens:
    - The app token comes from `POST https://id.twitch.tv/oauth2/token`
      (client_credentials).
    - The user token is `tokens.get("twitch")` and is refreshed with
      `grant_type=refresh_token` on a 401, then the call is retried once.
  - Headers on every call: `Client-Id`, `Authorization: Bearer`.

- [ ] **Step 1: Write failing tests (respx).**
  - `test_top_streams_sorted_and_limited`: 30 streams in the fixture with
    `top_n=25` gives 25 streams, sorted by viewers.
  - `test_top_streams_excludes_blocklist`.
  - `test_create_clip_returns_id`.
  - `test_create_clip_403_returns_none`.
  - `test_user_token_refreshed_on_401`: the first call gets 401, then a refresh,
    then a retry that gets 202; the TokenStore now holds the new token.
  - `test_wait_clip_times_out_returns_none` (patch sleep).
- [ ] **Step 2:** Run `pytest tests/test_twitch_api.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: twitch helix client`.

### Task 4: Clipper and scheduler

**Files:**
- Create: `clipbot/clipper.py`, `clipbot/scheduler.py`
- Test: `tests/test_clipper.py`, `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `Trigger`, `TwitchApi`, `Db`, `Moment`.
- Produces:
  - `Clipper(api, db, settings, now: Callable[[], datetime])` with
    `async handle(trigger: Trigger, stream: StreamInfo) -> Moment | None`:
    - enforces `max_clips_per_hour` using the count of moments in the last hour
    - inserts the moment as `pending`
    - `create_clip`, then `wait_clip`
    - sets status `ready` with `clip_url`, or `unusable`
  - `pick_winner(db, settings, now) -> Moment | None`:
    - looks at `ready` moments with `created_at ≥ now − render_interval_min`
    - picks the highest score
    - returns None if the best is below `min_post_score`, and marks that window's
      moments `skipped`

- [ ] **Step 1: Write failing tests** (fake API object).
  - `test_ready_moment_stored`.
  - `test_clip_disabled_marks_unusable`: `create_clip` returns None and the status
    is `unusable`; no exception.
  - `test_clip_never_appears_marks_unusable`.
  - `test_hourly_cap_blocks_41st_clip`.
  - `test_pick_highest_in_window`.
  - `test_ignores_older_than_window`.
  - `test_below_min_score_returns_none_and_skips`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: clip creation and render scheduling`.

### Task 5: Peak finder, hook picker, captions

**Files:**
- Create:
  - `clipbot/render/__init__.py`
  - `clipbot/render/peak.py`, `clipbot/render/hooks.py`, `clipbot/render/captions.py`
- Test: `tests/test_peak.py`, `tests/test_hooks.py`, `tests/test_captions.py`
- Fixture: `tests/conftest.py`:
  - `make_clip(tmp_path, seconds=20, loud_at=14.0, audio=True) -> Path`
  - it uses ffmpeg `testsrc2` at 1920×1080 with a quiet `sine` and a +30 dB burst
    from `loud_at` to `loud_at+1.5`

**Interfaces:**
- Produces:
  - `find_peak(path: Path, window_s=1.5) -> float`:
    - returns the start time of the loudest window
    - decodes mono 8 kHz `s16le` PCM through an ffmpeg pipe, computes RMS per
      0.1 s with the stdlib `array` module, and takes the max sliding sum over
      `window_s`
    - with no audio track: returns `max(0, duration*2/3 - window_s/2)`
  - `probe(path) -> ProbeInfo(duration: float, width: int, height: int, has_audio: bool)`
    via ffprobe JSON.
  - `HookPicker(templates: dict[str, list[tuple[str,str]]], recent_ids: list[str])`
    with `.pick(trigger_type, display_name) -> tuple[hook_id, text]`:
    - templates are `(id, text)` and `text` may contain `{name}`
    - the picker avoids ids in `recent_ids` (last 10) and falls back to `general`
      templates
    - it ships ≥8 templates per type, uppercase, with no emoji
  - `Word(start: float, end: float, text: str)`.
  - `transcribe(path) -> list[Word]`: faster-whisper `base`, `device="cpu"`,
    `compute_type="int8"`, `word_timestamps=True`. The model loads lazily and is
    cached.
  - `build_ass(words, offset_s: float, play_res=(1080,1920), caption_bottom_y: int) -> str`:
    - groups words into chunks of ≤3 words / ≤1.2 s
    - each word is shown as its own event with that word highlighted (yellow
      `&H00FFFF&`) and the others white
    - Montserrat/Arial Black, bold, size 78, outline 6
    - bottom-centre alignment with the baseline at `caption_bottom_y`
    - all times shifted by `offset_s`

- [ ] **Step 1: Write failing tests.**
  - `test_peak_finds_burst`: with `loud_at=14.0`, `abs(find_peak(p) - 14.0) <= 0.3`.
  - `test_peak_no_audio_falls_back`: a 12 s silent-track-less clip gives `≈ 7.25`.
  - `test_probe_reports_dimensions`.
  - `test_hook_avoids_recent`.
  - `test_hook_unknown_type_uses_general`.
  - `test_hook_fills_name`.
  - `test_templates_have_no_emoji` (all chars `< U+2000`).
  - `test_ass_offsets_and_highlight`: words at 1.0 s with offset 1.5 give a
    `Dialogue` starting at `0:00:02.50` that contains the highlight tag.
  - `test_ass_empty_words_has_header_only`.
  - `transcribe` is not unit tested (model download); it's covered by the Task 6
    integration test, which is marked `slow`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: peak detection, hooks and caption subtitles`.

### Task 6: Composer, render pipeline, safety

**Files:**
- Create: `clipbot/render/compose.py`, `clipbot/render/pipeline.py`, `clipbot/safety.py`
- Test: `tests/test_compose.py`, `tests/test_pipeline.py`, `tests/test_safety.py`

**Interfaces:**
- Consumes: `probe`, `find_peak`, `HookPicker`, `transcribe`, `build_ass`, `Db`,
  `Moment`, `Video`.
- Produces:
  - `Layout` constants:
    - `W,H = 1080,1920`
    - `TAG_BOTTOM = 1920-220`
    - `CAPTION_BOTTOM = TAG_BOTTOM - 110`
    - `HOOK_TOP = 220`
    - `HOOK_SECONDS = 3.0`
    - `COLD_OPEN = 1.5`
  - `build_ffmpeg_cmd(src, out, peak_s, info: ProbeInfo, hook_text, tag_text, ass_path, facecam: tuple|None, fonts_dir) -> list[str]`.
    The filter graph:
    1. Cold open: `trim` the 1.5 s peak, then a 0.15 s white `fade` flash, then
       `concat` with the full clip (video and audio; generate silent audio with
       `anullsrc` if `has_audio` is False).
    2. Background: scale to cover 1080×1920, crop, `boxblur=20:2`, then darken.
    3. Foreground:
       - no facecam: gameplay scaled to width 1080, overlaid at the vertical centre
       - with facecam: the facecam crop is scaled to 1080×640 at the top, and
         gameplay is scaled to fit 1080×1280 below it
    4. `subtitles=ass_path`.
    5. Hook: `drawtext` with box, centred, `y=HOOK_TOP`, `enable='lt(t,3.0)'`,
       wrapped to ≤18 chars per line.
    6. Tag: `drawtext` text `@<DisplayName>`, fontsize 56, white, `borderw=4`,
       `box=1:boxcolor=black@0.55:boxborderw=18`, centred,
       `y=TAG_BOTTOM-text_h`, for the whole video.
    7. Audio: `loudnorm=I=-14:TP=-1.5:LRA=11`.
    8. Encode: `-c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -movflags +faststart`.
  - `is_safe(words: list[Word], blocklist: list[str]) -> bool`: case-insensitive
    whole-word match.
  - `async render_moment(moment, settings, db, download: Callable[[str, Path], Path] = ytdlp_download) -> Video | None`:
    1. download (`yt-dlp -f best -o …`) into `data/tmp`
    2. probe; a clip under 3 s returns None and marks the moment `skipped`
    3. find the peak and transcribe
    4. pick a hook and build the ASS file, with offset = `COLD_OPEN + 0.15`
    5. run ffmpeg in `asyncio.to_thread`
    6. write the sidecar JSON with keys `streamer`, `display_name`, `clip_url`,
       `trigger_type`, `score`, `hook_text`, `title`, `description`, `hashtags`
       - title = hook text in title case
       - description has `@DisplayName`, `twitch.tv/<login>` and hashtags
       - hashtags are `["#GTA6","#GTAVI","#<login>","#gaming","#shorts"]`
    7. compute `safe` with `is_safe`, then add the `Video` row and mark the
       moment `rendered`
    8. delete the downloaded source

    Paths are `output/YYYY-MM-DD/HHMM_<login>.mp4` and `.json`.

- [ ] **Step 1: Write failing tests.**
  - `test_cmd_contains_tag_at_bottom`: the filter string contains `@StreamerName`
    and `y=1700-text_h`.
  - `test_cmd_hook_enabled_first_3s`: contains `lt(t,3.0)`.
  - `test_cmd_cold_open_trims_peak`: contains `trim=start=12.0:duration=1.5` for
    `peak_s=12.0`.
  - `test_cmd_facecam_layout_crops`: with facecam `(1500,40,380,220)` the filter
    contains `crop=380:220:1500:40`.
  - `test_cmd_no_audio_uses_anullsrc`.
  - `test_safe_blocks_listed_word`, `test_safe_ignores_substring` ("class" is not
    blocked by "ass"), `test_safe_empty_transcript_true`.
  - `test_render_end_to_end` (`@pytest.mark.slow`):
    - `make_clip(20s, loud_at=14)`, with transcribe monkeypatched to return 3 words
    - the output probes as 1080×1920
    - duration ≈ 20 + 1.5 + 0.15 (±0.5)
    - sidecar `description` contains `@StreamerName`
    - the source is deleted
  - `test_render_empty_transcript_renders` (slow): transcribe returns `[]`, the
    output exists and `safe is True`.
  - `test_render_too_short_skips`: a 2 s clip gives None and the moment `skipped`.
- [ ] **Step 2:** Run `pytest tests/test_compose.py tests/test_pipeline.py tests/test_safety.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement. Ship `clipbot/render/fonts/` with an OFL bold font
  (Montserrat ExtraBold), passed via `fontfile=` and the subtitles `fontsdir=`.
- [ ] **Step 4:** Run the tests, including `-m slow`. Expected: PASS.
- [ ] **Step 5:** Save a frame at t=0.5 s and one at t=10 s from the e2e output to
  `data/preview/` for visual inspection, and view them. The tag must be visible
  bottom-centre and the hook text at the top in the first frame.
- [ ] **Step 6:** Commit: `feat: vertical short renderer with hook, captions and streamer tag`.

### Task 7: Publish planner and publisher interface

**Files:**
- Create: `clipbot/publish/__init__.py`, `clipbot/publish/base.py`, `clipbot/publish/planner.py`
- Test: `tests/test_planner.py`

**Interfaces:**
- Consumes: `Db`, `Video`, `Post`, `Settings`.
- Produces:
  - `class AuthError(Exception)`.
  - `PostResult(remote_id: str, url: str | None)`.
  - `Publisher` Protocol with `name: str` and
    `async publish(video_path: Path, meta: dict) -> PostResult`
    (raises `AuthError` for auth failures and other exceptions for transient ones).
  - `due_platforms(db, settings, now) -> list[str]`. A platform is due when all of
    these hold:
    - it's enabled and not `disabled:<platform>` in state
    - it's not inside the quiet hours (local time)
    - it has fewer posts with status `ok` in the last 24 h than its budget
    - its last ok post was at least `24h / budget` ago
  - `choose_video(db, platform, settings, now) -> Video | None`: the highest score
    among videos with `safe` true, `created_at ≥ now − freshness_hours`, and an id
    not in `posted_video_ids(platform)`.
  - `async publish_once(db, settings, publishers: dict[str, Publisher], now)`:
    - for each due platform, choose a video and publish
    - on success, record an `ok` Post
    - on `AuthError`, `set_state("disabled:<p>", reason)`, log it, and continue
      with the other platforms
    - on another exception, retry up to 3× with backoff 5/20/60 s (injectable
      `sleep`), then record a `failed` Post
    - failed posts don't count toward the budget, and the same video can be
      retried at the next slot

- [ ] **Step 1: Write failing tests.**
  - `test_budget_reached_not_due`: 6 ok YouTube posts in 24 h means YouTube isn't due.
  - `test_min_gap_enforced`: with budget 6, the last post 3 h ago means not due;
    5 h ago means due.
  - `test_quiet_hours`.
  - `test_disabled_platform_not_due`.
  - `test_choose_skips_unsafe_stale_and_already_posted`.
  - `test_restart_does_not_double_post`: build a new `Db` object on the same file
    after a post; `choose_video` doesn't return the same video for that platform.
  - `test_auth_error_disables_only_that_platform`: YouTube raises `AuthError` and
    TikTok succeeds; state has `disabled:youtube` and TikTok has an ok post.
  - `test_transient_error_retries_then_records_failed`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: publish planner with budgets, spacing and failure isolation`.

### Task 8: Platform publishers and OAuth login

**Files:**
- Create: `clipbot/publish/youtube.py`, `clipbot/publish/tiktok.py`, `clipbot/publish/instagram.py`
- Modify: `clipbot/oauth.py`, adding `async run_oauth(provider: str, settings, tokens) -> None`
- Test: `tests/test_youtube.py`, `tests/test_tiktok.py`, `tests/test_instagram.py`, `tests/test_oauth.py`

**Before coding:** check each platform's current official docs for the endpoints and
scopes below, and record any differences in the README.

**Interfaces:**
- Consumes: the `Publisher` protocol, `PostResult`, `AuthError`, `TokenStore`.
- Produces:
  - `YouTubePublisher(tokens, client)`:
    - refreshes the Google token (`https://oauth2.googleapis.com/token`)
    - starts a resumable upload with
      `POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status`
      - snippet: `title` (≤100 chars, ends with ` #Shorts`), `description`,
        `tags`, `categoryId "20"`
      - status: `privacyStatus` from settings (default `public`),
        `selfDeclaredMadeForKids false`
    - PUTs the bytes
    - returns the id and `https://youtube.com/shorts/<id>`
    - raises `AuthError` on 401/403 after a refresh attempt fails or `invalid_grant`
  - `TikTokPublisher(tokens, client)`:
    - refreshes via `https://open.tiktokapis.com/v2/oauth/token/`
    - `POST /v2/post/publish/creator_info/query/`, then picks `privacy_level`:
      `PUBLIC_TO_EVERYONE` if offered, else `SELF_ONLY`
    - `POST /v2/post/publish/video/init/` with `source_info.source = "FILE_UPLOAD"`
      and chunking (chunk size 10 MB, single chunk if smaller)
    - PUTs the chunks with `Content-Range`
    - polls `/v2/post/publish/status/fetch/` until `PUBLISH_COMPLETE` or a failure
      (timeout 5 min)
    - returns the `publish_id`
  - `InstagramPublisher(tokens, client)`:
    - `POST /{ig-user-id}/media` with `media_type=REELS`, `upload_type=resumable`,
      `caption`
    - POSTs the file to the returned `uri` (`rupload.facebook.com`) with
      `Authorization: OAuth <token>`, `offset: 0` and `file_size`
    - polls `GET /{container}?fields=status_code` until `FINISHED` (timeout 5 min)
    - `POST /{ig-user-id}/media_publish`
    - the long-lived token is refreshed when under 7 days remain
    - uses Graph API version `v21.0` (configurable)
  - `run_oauth(provider, settings, tokens)`:
    - starts a local HTTP server on `http://localhost:8765/callback`
    - prints the authorize URL and opens a browser if possible
    - exchanges the code and stores the token under the provider name
    - Instagram exchanges for a long-lived token and looks up
      `/me/accounts?fields=instagram_business_account` to store the `ig_user_id`
    - scopes:
      - Twitch: `clips:edit`
      - Google: `https://www.googleapis.com/auth/youtube.upload`
      - TikTok: `user.info.basic,video.publish`
      - Facebook: `instagram_basic,instagram_content_publish,pages_show_list,business_management`
    - client IDs/secrets come from `.env`:
      - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
      - `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`
      - `META_APP_ID`, `META_APP_SECRET`
- Each publisher builds its caption from the sidecar meta: title, description and
  hashtags, always including `@DisplayName`.

- [ ] **Step 1: Write failing tests (respx).**
  - `test_youtube_upload_happy_path`: the init request body has a title ending
    `#Shorts` and a description containing `@StreamerName`; the result URL is
    `https://youtube.com/shorts/abc`.
  - `test_youtube_invalid_grant_raises_auth_error`.
  - `test_tiktok_uses_self_only_when_public_not_offered`.
  - `test_tiktok_chunks_large_file` (25 MB sparse temp file → 3 PUTs with correct
    `Content-Range`).
  - `test_tiktok_failed_status_raises`.
  - `test_instagram_container_poll_then_publish`.
  - `test_instagram_error_status_raises`.
  - `test_oauth_builds_authorize_url_with_scopes` for each provider (pure URL
    builder `authorize_url(provider, settings, state) -> str`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: youtube, tiktok and instagram publishers with oauth login`.

### Task 9: App loop, CLI, status, housekeeping, deployment, README

**Files:**
- Create:
  - `clipbot/app.py`, `clipbot/cli.py`, `clipbot/housekeeping.py`
  - `deploy/clipbot.service`, `Dockerfile`
- Modify: `README.md`, `.env.example`
- Test: `tests/test_housekeeping.py`, `tests/test_cli.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `cleanup(settings, now)`:
    - deletes `output/*` day folders older than `keep_days`
    - deletes `data/tmp/*` older than 1 h
    - log rotation is a `RotatingFileHandler` with 10 MB × 5 at `data/clipbot.log`
  - `status_report(db, settings, now) -> str`. Lines:
    - `Watching: N streams` (from state `watching`)
    - moments in the last hour, as counts by status
    - videos made today
    - for each platform: `posted today X/budget`, or `DISABLED: <reason>`, or `off`
    - the last 5 errors (state `last_errors`, a JSON list)
  - `async run(settings)` starts tasks:
    - discovery loop: refreshes `streams: dict[login, StreamInfo]` and sets state
      `watching`
    - `ChatListener`, feeding `HypeDetector`; triggers are scheduled as
      `Clipper.handle`
    - the detector `tick` runs every second
    - render loop: every `render_interval_min`, `pick_winner` then `render_moment`
    - publish loop: every 60 s, `publish_once`
    - housekeeping: hourly
    - each loop is wrapped so an exception is logged, appended to `last_errors`,
      and the loop continues
  - CLI (argparse):
    - `clipbot run`
    - `clipbot auth {twitch,youtube,tiktok,instagram}`
    - `clipbot render <clip_url> [--name DisplayName]`
    - `clipbot status`
    - global `--config config.yaml`

- [ ] **Step 1: Write failing tests.**
  - `test_cleanup_removes_old_days_only`.
  - `test_status_shows_budget_and_disabled`.
  - `test_cli_status_runs` (subprocess-free: call `main(["status"])` with a temp DB
    and capture stdout).
  - `test_loop_survives_exception`: the wrapped loop body raises once, then
    succeeds; the error is recorded and the second iteration runs.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
  - `deploy/clipbot.service`: `Restart=always`, `RestartSec=10`,
    `WorkingDirectory`, `EnvironmentFile=.env`.
  - `Dockerfile`: `python:3.12-slim` + `apt-get install ffmpeg`, then `pip install .`.
  - README: what it does, the user setup checklist (Twitch / Google / TikTok /
    Meta steps, including Google's "In production" status and the audit forms),
    install, config, the auth commands, running as a service
    (systemd / Docker / Windows Task Scheduler / launchd), status, and the
    rights/copyright notes.
- [ ] **Step 4:** Run the full suite with `pytest -v` (plus `pytest -m slow`). Expected: all PASS.
- [ ] **Step 5: Manual smoke.**
  1. Run `clipbot render <a public twitch clip URL>` and view frames of the output.
  2. Run `clipbot run` for 2 minutes without Twitch credentials. Expected: a logged
     auth error for discovery, other loops alive, and `clipbot status` prints.
  3. If the network blocks Twitch, record that the smoke was not possible.
- [ ] **Step 6:** Commit: `feat: app runner, cli, status, housekeeping and deployment`.
