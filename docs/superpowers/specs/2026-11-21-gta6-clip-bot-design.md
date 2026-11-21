# GTA 6 Hype Clip Bot — Design

Date: 2026-11-21
Status: draft, awaiting approval

## Intent

A bot that watches GTA 6 streams from the most popular Twitch streamers, notices
when something exciting happens, and every 10 minutes turns the best moment into a
polished vertical short (TikTok / YouTube Shorts / Reels) that opens with a hook.
It must cost as close to nothing as possible to run.

## Goals

- Cover all of the top live GTA 6 streams on Twitch at once (default: top 25 by viewers).
- Detect hype moments from chat activity.
- Every 10 minutes, output one finished 9:16 video built from the strongest moment
  of that window.
- Every video opens with a hook: a 1–2 s cold open of the peak moment plus on-screen
  hook text, then the clip plays from the build-up.
- Burned-in word-by-word captions and a visible streamer credit.
- Zero paid services.

- Fully autonomous: it runs unattended and posts the best videos to YouTube Shorts,
  TikTok and Instagram Reels without anyone reviewing them first.

## Non-goals (v1)

- Posting every video. Only the best ones are posted, within each platform's limits.
- Platforms other than Twitch (Kick, YouTube Live).
- Recording streams continuously.
- Automatic webcam detection (per-streamer webcam crop can be set by hand in config).
- Emoji in on-screen text (ffmpeg can't render color emoji reliably).

## Anti-goals (would count as failure even if it "works")

- Filler: posting a weak video just because 10 minutes passed. Skip the slot instead.
- Videos without the streamer's tag at the bottom.
- Hammering Twitch's API or spamming clips on a streamer's channel.
- Anything that costs money per video.
- Spam-like posting that gets the accounts flagged.
- Auto-posting a clip with slurs in it.

## Constraints

- Must run on the user's own computer or a cheap always-on server. Cloud workspaces
  that sleep are unsuitable.
- Needs: Python 3.11+, ffmpeg on PATH, a free Twitch developer application
  (client ID + secret), and a Twitch account to create clips under.
- Clips created through the API are public on the streamer's channel and attributed
  to that Twitch account.
- Reposting other streamers' content is common in this niche but the content is theirs;
  credit is always shown.
- Platform posting rules (from memory, to be checked against current docs when building):
  - **YouTube:** Data API v3 uploads cost ~1,600 of the default 10,000 daily
    quota units, so about 6 uploads a day. Uploads from an unverified API project
    are forced private until Google audits the project.
  - **TikTok:** Content Posting API (Direct Post). Until the app passes TikTok's
    audit, posts can only be private (`SELF_ONLY`).
  - **Instagram:** Graph API Reels publishing needs a Business or Creator account
    linked to a Facebook Page, with a cap of about 50 posts per 24 hours.
- Streamers' background music can trigger copyright claims on posted videos. There's
  no free fix; the bot records claims/failures in its log.

## Approaches considered

| | Approach | Trade-off |
|---|---|---|
| **A (chosen)** | Read chat on every stream; on a spike, create a Twitch clip via API, download only the winning clip, edit locally. | Light bandwidth, covers all big streamers, free. Clip length/timing set by Twitch; some streamers disable clipping. |
| B | Record every stream into a rolling buffer and cut locally. | Exact control, but ~6 Mbps per stream, ~120 Mbps for 20 streams around the clock. |
| C | Chat on all, record the top ~5. | Best quality on the biggest names, most complex. |

The user chose the cheapest option, which is A.

## How it works

Python 3.11, single asyncio process, SQLite for state. Components:

### 1. Stream discovery
- App access token (client-credentials) → Helix `Get Games` to resolve the
  "Grand Theft Auto VI" game ID (configurable name/ID).
- Helix `Get Streams?game_id=…` sorted by viewers; take the top `TOP_N` (default 25).
- Refresh every 5 minutes; join/part chat channels as the list changes.

### 2. Chat listener
- Anonymous read-only Twitch IRC over WebSocket (`justinfan<random>` login, no token).
- Per channel, count messages in 5-second buckets, plus unique chatters and hits on
  hype/laugh emotes and words (`LUL`, `OMEGALUL`, `KEKW`, `LMAO`, `Pog`, `PogChamp`,
  `W`, `HOLY`, `???`, `clip it`, …; list in config).

### 3. Hype detector
- Baseline = exponential moving average of the message rate over ~5 minutes per channel.
- Score per bucket = (rate / baseline), boosted by emote share and unique-chatter share.
  Normalising against each channel's own baseline stops the biggest channels from
  always winning.
- Trigger when score ≥ `HYPE_THRESHOLD` (default 3.0) for 2 consecutive buckets.
- Tag each trigger with a type: `funny` (laugh emotes dominate), `hype`
  (Pog/W/HOLY dominate), `shock` (`???`, `WHAT`), or `general`.
- Per-channel cooldown of 120 s; global cap of 40 clip creations per hour.

### 4. Clipper
- On trigger, call Helix `Create Clip` immediately with a user token (`clips:edit`).
  Chat reacts 5–15 s after the event, and a Twitch clip captures the preceding
  seconds of the stream, so creating it at spike time catches the moment.
- Poll `Get Clips?id=…` until it's ready (up to ~20 s). If the channel blocks
  clipping or creation fails, mark the moment as unusable and move on.
- Store a "moment" row: channel, trigger type, score, time, clip ID/URL, chat
  snippet. **Nothing is downloaded at this stage.**

### 5. Scheduler (every 10 minutes)
- Choose the highest-scoring unused moment from the last 10 minutes whose clip is ready.
- If none reaches `MIN_POST_SCORE`, skip this slot and log it.
- Hand the winner to the renderer.

### 6. Renderer (ffmpeg + faster-whisper, all local)
1. Download the clip at source quality with `yt-dlp`.
2. **Find the peak:** loudest ~1.5 s window of audio (ffmpeg `astats`/`ebur128`),
   which falls back to the last third of the clip.
3. **Transcribe** with faster-whisper (`base` model, CPU, word timestamps).
4. **Compose** 1080×1920, 30/60 fps:
   - Background: gameplay scaled to fill and blurred.
   - Foreground: gameplay scaled to full width, centred.
   - If the streamer has a `facecam` crop in config: webcam on top, gameplay below
     (split layout).
5. **Hook:**
   - Cold open: the 1.5 s peak segment first, a quick flash/whoosh transition, then
     the clip from the start.
   - Hook text, big and bold at the top for the first ~3 s. It comes from a template
     bank keyed by trigger type (e.g. funny → "I can't stop laughing at this",
     hype → "This is actually insane", shock → "Nobody expected this"), optionally
     filled with the streamer's name. A template isn't reused within the last 10 videos.
6. **Captions:** word-by-word burned-in subtitles (ASS, thick outline, current word
   highlighted), placed in the lower third above the streamer tag.
7. **Streamer tag:** the streamer's tag (`@<DisplayName>`, e.g. `@StreamerName`)
   sits at the bottom centre of the frame for the whole video. It's in bold white
   with a dark outline and a semi-transparent pill behind it, inside the platforms'
   safe area so TikTok/Shorts buttons don't cover it. Captions sit just above it.
8. Loudness-normalise the audio to about −14 LUFS and encode H.264/AAC at a high
   bitrate for upload.

### 7. Output
- `output/YYYY-MM-DD/HHMM_<streamer>.mp4`
- Sidecar `…json` with the streamer, source clip URL, trigger type, score, a
  suggested title, a description with credit, and hashtags (`#GTA6 #<streamer> …`).

### 8. Safety check (before anything is posted)
- If the transcript contains a word from a configurable blocklist (slurs and similar),
  the video is saved but never posted.

### 9. Publisher
- Each platform (YouTube, TikTok, Instagram) is a separate plug-in with its own
  on/off switch in config, so a platform can be switched on once its app is approved.
- Each platform has a daily budget. Defaults:
  - YouTube: 6
  - TikTok: 10
  - Instagram: 20

  Posts are spread evenly through the day (minimum gap = 24 h ÷ budget), with an
  optional quiet window (e.g. 3–8 am local).
- When a platform's slot comes up, it posts the highest-scoring video from the last
  6 hours that hasn't been posted there yet and passed the safety check. The same
  video can go to all three platforms.
- Per platform:
  - **YouTube:** `videos.insert` resumable upload, OAuth (installed-app flow).
    Title from the hook text plus `#Shorts`; description with the streamer's tag,
    the source clip link and hashtags.
  - **TikTok:** Content Posting API Direct Post with chunked `FILE_UPLOAD`. Query
    `creator_info` first and use an allowed privacy level (public once audited).
  - **Instagram:** Graph API Reels container (resumable upload of the local file),
    poll the container until it's finished, then `media_publish`.
- A `posts` table records the platform, video, post ID/URL and status. Failed uploads
  are retried up to 3 times with backoff. If authentication fails, that platform is
  switched off and the error is logged, and the other platforms keep running.

### 10. Running unattended
- Runs as a long-lived service: a systemd unit on Linux, with a Dockerfile as an
  alternative and instructions for Windows Task Scheduler / macOS launchd.
  It restarts automatically on crash.
- All OAuth tokens refresh automatically. One-time login commands for each platform.
- Housekeeping:
  - delete downloaded source clips after rendering
  - delete rendered videos older than 7 days (configurable)
  - rotate logs
- A `clipbot status` command shows: streams being watched, moments found, videos
  made, posts per platform today, and the last errors.

### Config
- `.env`: `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TWITCH_USER_REFRESH_TOKEN`.
- `config.yaml`: `TOP_N`, game name, interval (10 min), thresholds, emote lists,
  hook templates, per-streamer facecam crops, and an optional blocklist of channels.
- A one-time `auth` command runs the Twitch OAuth flow and stores the refresh token.

### CLI
- `clipbot run` starts the bot.
- `clipbot auth twitch|youtube|tiktok|instagram` handles the one-time logins.
- `clipbot status` shows a health summary.
- `clipbot render <clip_url>` renders a single clip by hand (useful for testing
  the look).

## Testing

- Unit tests:
  - hype scoring and trigger logic on recorded or synthetic chat
  - trigger-type tagging
  - scheduler picking and skipping
  - hook template rotation
  - ffmpeg filter graph construction
- Integration test: render a synthetic clip (ffmpeg `testsrc` plus a tone with a
  loud spike) end-to-end and check the output is 1080×1920 and the cold open comes
  first.
- Twitch calls are mocked in tests.

## Calls made by Claude (not decided by the user)

- Twitch only, top 25 streams, 10-minute slots, and skip a slot rather than post filler.
- The user chose fully autonomous posting to YouTube, TikTok and Instagram.
  Claude chose the defaults:
  - daily budgets: YouTube 6, TikTok 10, Instagram 20
  - a 6-hour freshness window for videos that can be posted
  - a slur blocklist
  - each platform has its own switch
- Hook = cold open of the loudest moment plus template text (free) rather than
  AI-written text (paid).
- Captions use local faster-whisper.
- No emoji in on-screen text.
- Webcam split layout only when a crop is configured.
- Python + ffmpeg + SQLite.

## Left to the builder

- Exact emote lists, threshold tuning, and caption styling details.
- Whether the current Create Clip API accepts a duration parameter (use it if
  available, default ~30 s).
- Handling of token refresh and API rate-limit headers.
- Checking current platform API limits and requirements, and adjusting the default
  budgets to match.
