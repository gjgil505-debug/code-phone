# clipbot: autonomous GTA 6 hype clips

clipbot watches the 25 biggest live GTA 6 streams on Twitch and reads their chat. When a chat suddenly
explodes, it makes a Twitch clip of the moment. Every 10 minutes it turns the best moment into a vertical
short, and it posts the best of those to YouTube Shorts, TikTok and Instagram Reels by itself, at
random, human-looking times.

Every video has:

- **A hook:** the loudest 1.5 seconds plays first, then a quick flash, then the whole clip. Big hook text
  ("NOBODY EXPECTED THIS") sits at the top for the first 3 seconds.
- **Word-by-word captions,** generated on your computer.
- **The streamer's tag** (`@StreamerName`) at the bottom for the whole video.
- **The streamer's webcam on top,** if you set where their webcam is on screen.

It doesn't use any paid AI services. The platforms' APIs are free.

---

## Phone-only setup (no computer needed)

You can do everything from your phone. The bot lives on a free cloud server and you control it with a
terminal app.

### A. Get a free server (Oracle Cloud "Always Free")
1. In your phone's browser, open <https://www.oracle.com/cloud/free/> and sign up for the free tier.
   - They ask for a card to verify you. The Always Free resources aren't charged.
   - Pick a home region near you. It can't be changed later.
2. Install **Termius** from the App Store or Play Store. It's free.
3. In Termius, make an SSH key: **Keychain → + → Generate Key** (type ED25519). Open the key and
   copy its **public key**.
4. In the Oracle console, create a server: **Compute → Instances → Create instance**.
   - Image: **Canonical Ubuntu 24.04**.
   - Shape: **Ampere → VM.Standard.A1.Flex**, 4 OCPUs and 24 GB memory. Both are inside the free
     allowance.
   - SSH keys: choose **Paste public keys** and paste the key from step 3.
   - Create it, then copy its **Public IP address**.
   - If Oracle says it's **out of capacity**, try again later or try a different availability domain.
     A paid fallback is a Hetzner CAX11 server, about 4 euros a month, set up the same way.
5. In Termius, add a host:
   - Address: the public IP.
   - Username: `ubuntu`.
   - Key: the one from step 3.

   Tap the host to connect. You're now typing on the server.

### B. Install clipbot (one command)
Your GitHub repo is **private**, so the server needs permission to download it. Pick one:
- **Easiest:** make the repo public. On github.com in your phone's browser, open the repo, then
  **Settings → General → Danger Zone → Change visibility → Public**. No passwords or keys are ever
  stored in the repo. Then paste this into Termius:
  ```
  curl -fsSL https://raw.githubusercontent.com/gjgil505-debug/code-phone/main/deploy/install.sh | bash
  ```
- **Keep it private:** on github.com, open **Settings → Developer settings → Fine-grained tokens →
  Generate new token**. Give it access to only this repo, with **Contents: Read-only**. Then paste
  these two lines, putting your token in place of `YOUR_TOKEN`:
  ```
  export GITHUB_TOKEN=YOUR_TOKEN
  curl -fsSL -H "Authorization: token $GITHUB_TOKEN" https://raw.githubusercontent.com/gjgil505-debug/code-phone/main/deploy/install.sh | bash
  ```

### C. Enter your keys and log in
1. Make the developer apps in steps 3–6 below. Do it in your phone's browser; the redirect URL is
   still `http://localhost:8765/callback`.
2. In Termius, run `cd ~/clipbot` then `clipbot setup`. It asks for each key one at a time:
   long-press to paste.
3. Run each `clipbot auth ...` command it lists, one at a time. Each prints a link. For each:
   - Open the link on your phone and approve.
   - Your browser then goes to a `localhost` page that **won't load**. That's expected.
   - Copy the whole address from the address bar and paste it back into Termius.
4. Start the bot with `sudo systemctl restart clipbot`, then check on it with `clipbot status`.

It now runs all the time. It restarts by itself if it crashes or the server reboots, and you can
close Termius. To check on it later, reconnect in Termius and run `clipbot status`.

---

## What you need to do

### 1. A computer that stays on (skip if you followed the phone-only setup)
- A PC, Mac, Linux box or small server that runs all day, every day, on stable internet
  (about 4–6 GB of traffic a day).
- About 20 GB of free disk space and a decent processor.
- Install **Python 3.11+** and **ffmpeg**:
  - Windows: `winget install Gyan.FFmpeg`
  - Mac: `brew install ffmpeg`
  - Ubuntu: `sudo apt install ffmpeg`

### 2. Install clipbot
```bash
git clone <this repo> clipbot && cd clipbot
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install .
cp .env.example .env                 # your keys go here
cp config.example.yaml config.yaml   # your settings go here
```
The first video downloads the speech-to-text model (about 150 MB) automatically.

### 3. Twitch (finding and clipping moments)
1. Make a Twitch account and turn on **two-factor authentication** (the developer console requires it).
2. Go to <https://dev.twitch.tv/console> and choose **Register Your Application**.
   - Name: anything.
   - OAuth Redirect URL: `http://localhost:8765/callback`
   - Category: Other. Client type: Confidential.
3. Copy the **Client ID** and a new **Client Secret** into `.env` as `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`.
4. Run `clipbot auth twitch` and approve in the browser.

Clips are created under this Twitch account, so they appear publicly on the streamers' channels.

### 4. YouTube Shorts
1. Make the YouTube channel the Shorts will go to.
2. At <https://console.cloud.google.com>:
   - Create a project.
   - Go to **APIs & Services → Library** and enable **YouTube Data API v3**.
3. Under **OAuth consent screen**:
   - User type: External.
   - Add your Google account as a test user.
   - **Set Publishing status to "In production".** If you skip this, Google logs the bot out every 7 days.
4. Under **Credentials → Create credentials → OAuth client ID**, choose type **Desktop app**. Copy the
   ID and secret into `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
5. Run `clipbot auth youtube`.
6. Fill in the **YouTube API Services audit and quota extension form**. Until Google approves it:
   - videos uploaded through the API stay **private**
   - the free quota covers only about **6 uploads a day**

### 5. TikTok
1. Make the TikTok account for the channel.
2. At <https://developers.tiktok.com>:
   - Create an app.
   - Add the **Login Kit** and **Content Posting API** products, and turn on **Direct Post**.
   - Request the scopes `user.info.basic` and `video.publish`.
3. Redirect URI: add `http://localhost:8765/callback`. If TikTok only accepts `https://` addresses, add
   any page you own, e.g. `https://yoursite.com/callback`. When you log in, clipbot will ask you to paste
   the address your browser ended up on.
4. Copy the Client Key and Secret into `.env` as `TIKTOK_CLIENT_KEY` and `TIKTOK_CLIENT_SECRET`.
5. Run `clipbot auth tiktok`. If you used an https address in step 3, run
   `clipbot auth tiktok --redirect-uri https://yoursite.com/callback` instead.
6. **Submit the app for review.** TikTok asks for:
   - a website, a privacy policy and terms of service
   - a short demo video of the app

   Until it's approved, posts are **private** (only you can see them).

### 6. Instagram Reels
1. In the Instagram app, switch your account to **Professional** (Creator or Business).
2. **Link it to a Facebook Page.** You can do this from Instagram's settings or the Page's settings.
3. At <https://developers.facebook.com>:
   - Create an app of type Business and add **Instagram** (API setup with Facebook login).
   - Add `http://localhost:8765/callback` as a valid OAuth redirect URI.
   - Make sure you're an admin of the app.
4. Copy the App ID and Secret into `.env` as `META_APP_ID` and `META_APP_SECRET`.
5. Run `clipbot auth instagram`. While the app is in development mode, it can post to accounts that have
   a role on the app, which includes yours.

### 7. Turn posting on and start it
Edit `config.yaml`:
```yaml
enabled:
  youtube: true
  tiktok: true
  instagram: true
```
Then:
```bash
clipbot run      # leave it running
clipbot status   # in another window, any time
```
To check how videos look before going live: `clipbot render https://clips.twitch.tv/SomeClip --name StreamerName`.
Test renders are never posted.

### 8. Keep it running by itself
Pick the option that matches your computer:
- **Linux:** edit `deploy/clipbot.service` (user and paths), copy it to `/etc/systemd/system/`, then
  run `sudo systemctl enable --now clipbot`.
- **Docker:**
  - Build with `docker build -t clipbot .`
  - Run with
    `docker run -d --restart=always --env-file .env -v $PWD/data:/app/data -v $PWD/output:/app/output -v $PWD/config.yaml:/app/config.yaml clipbot`
  - Do the `clipbot auth ...` logins on the host first. They're saved in `data/tokens.json`.
- **Windows:**
  - Open Task Scheduler and choose Create Task.
  - Trigger: "At log on".
  - Action: start `<folder>\.venv\Scripts\clipbot.exe` with argument `run` and "Start in" set to the
    clipbot folder.
  - Settings: "If the task fails, restart every 1 minute".
- **Mac:** a launchd agent with `KeepAlive` true that runs `.venv/bin/clipbot run` from the folder.

### 9. Now and then
- Run `clipbot status`. It shows:
  - the streams being watched and the hype moments found
  - posts per platform today and roughly when the next one goes out, plus anything paused
  - recent problems
- If a platform shows **PAUSED**, its login broke. Run `clipbot auth <platform>` and posting resumes.
- Finished videos are kept for 7 days in `output/`, then deleted (setting: `keep_days`).
- Expect the occasional copyright claim over music in the background of a stream.
- If a streamer asks you not to repost them, add their Twitch login to `channel_blocklist` in `config.yaml`.

---

## How it decides

- **Hype:** each channel's chat speed is compared with its own normal speed over the last 5 minutes.
  A moment counts when chat is about 3× busier than normal for 10 seconds, and extra weight goes to
  emotes like KEKW, Pog and ???. The emote type decides whether the moment is *funny*, *hype* or *shock*,
  which picks the style of hook. There's at most one clip per channel every 2 minutes, and 40 per hour
  in total.
- **Every 10 minutes:** the strongest moment of that window becomes a video. If nothing was strong
  enough, it skips the slot instead of making filler.
- **Posting like a person, not a bot:**
  - Each day, every platform gets a random number of posts, well under its limits: YouTube 2–4,
    TikTok 3–6, Instagram 2–5.
  - Posts go out at random times between 10am and 11pm your time, at least 45 minutes apart.
  - Two platforms never post within 10 minutes of each other.
  - Captions and hashtags are worded a little differently every time.
  - Hard caps of 6 / 10 / 20 posts in any 24 hours stay in place as a safety net.
  - Each post uses the highest-scoring unposted video from the last 6 hours.
- **Word filter:** if the captions contain a slur, the video is kept but never posted. Edit the list
  with `blocklist:` in `config.yaml`.
- **Failures:** each platform runs on its own. If one login expires, only that platform pauses.
  Uploads that fail are retried 3 times.

All settings are explained in `config.example.yaml`.

## Notes
- The platform APIs change often. clipbot was written against the documented APIs as of late 2026.
  If a platform starts failing, `clipbot status` and `data/clipbot.log` show its exact error.
- These are other streamers' videos. Every post credits them with their tag and a link to their
  channel, but they own the content.

## Development
```bash
pip install -e ".[dev]"
pytest            # all tests; the "slow" ones render real video with ffmpeg
pytest -m "not slow"
```
