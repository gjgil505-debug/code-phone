"""Moment -> finished vertical short + sidecar metadata."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from clipbot.config import Settings
from clipbot.db import Db, Moment, Video
from clipbot.render.captions import Word, build_ass, transcribe
from clipbot.render.compose import CAPTION_BOTTOM, COLD_OPEN, FLASH, build_ffmpeg_cmd
from clipbot.render.hooks import DEFAULT_HOOKS, HookPicker
from clipbot.render.peak import find_peak, probe
from clipbot.safety import is_safe

log = logging.getLogger(__name__)
MIN_CLIP_S = 3.0


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ytdlp_download(url: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    out = subprocess.run([sys.executable, "-m", "yt_dlp", "-q", "--no-warnings", "--no-playlist", "-f", "best",
                          "-o", str(dest / "%(id)s.%(ext)s"), "--print", "after_move:filepath", url],
                         check=True, capture_output=True, text=True, timeout=300).stdout
    return Path(out.strip().splitlines()[-1])


DESCRIPTIONS = [
    "{title}\n\nStreamer: @{name} - watch them live at twitch.tv/{login}",
    "@{name} had chat going crazy with this one\n\nfull streams at twitch.tv/{login}",
    "{title} | @{name}\n\ncatch {name} live on twitch.tv/{login}",
    "this clip from @{name} though\n\ntwitch.tv/{login}",
    "{title}\n\nclip: @{name} (twitch.tv/{login})",
    "chat lost it at this @{name} moment\n\nlive at twitch.tv/{login}",
]
EXTRA_TAGS = ["#GTAVI", "#gta", "#gaming", "#shorts", "#fyp", "#twitch", "#gta6clips", "#rockstargames"]


def _metadata(m: Moment, hook_text: str, rng: random.Random | None = None) -> dict:
    """Title/description/hashtags, worded a little differently each time so posts don't look templated."""
    rng = rng or random.Random()
    title = hook_text.title()
    hashtags = ["#GTA6", f"#{m.channel}", *rng.sample(EXTRA_TAGS, rng.randint(2, 4))]
    rng.shuffle(hashtags)
    description = (rng.choice(DESCRIPTIONS).format(title=title, name=m.display_name, login=m.channel)
                   + "\n\n" + " ".join(hashtags))
    return {"streamer": m.channel, "display_name": m.display_name, "clip_url": m.clip_url,
            "trigger_type": m.trigger_type, "score": m.score, "hook_text": hook_text, "title": title,
            "description": description, "hashtags": hashtags}


def _out_path(settings: Settings, m: Moment, now: datetime) -> Path:
    day = settings.output_dir / now.strftime("%Y-%m-%d")
    day.mkdir(parents=True, exist_ok=True)
    base = f"{now.strftime('%H%M')}_{m.channel}"
    path, n = day / f"{base}.mp4", 1
    while path.exists():
        n += 1
        path = day / f"{base}_{n}.mp4"
    return path


def _render_sync(m: Moment, settings: Settings, db: Db, src: Path, work: Path,
                 transcriber: Callable[[Path], list[Word]], now: datetime) -> Video | None:
    info = probe(src)
    if info.duration < MIN_CLIP_S:
        log.info("clip %s too short (%.1fs); skipping", m.clip_url, info.duration)
        db.set_moment_status(m.id, "skipped")
        return None
    peak = find_peak(src, COLD_OPEN)
    words = transcriber(src)
    hook_id, hook_text = HookPicker(DEFAULT_HOOKS, db.recent_hook_ids(10)).pick(m.trigger_type, m.display_name)
    ass = work / "subs.ass"
    ass.write_text(build_ass(words, COLD_OPEN + FLASH, caption_bottom_y=CAPTION_BOTTOM), encoding="utf-8")
    out = _out_path(settings, m, now)
    cmd = build_ffmpeg_cmd(src, out, peak, info, hook_text, f"@{m.display_name}", ass,
                           settings.facecams.get(m.channel), work)
    subprocess.run(cmd, check=True, capture_output=True, timeout=900)
    meta_path = out.with_suffix(".json")
    meta_path.write_text(json.dumps(_metadata(m, hook_text), indent=2))
    v = Video(None, m.id, str(out), str(meta_path), m.score, hook_id, is_safe(words, settings.blocklist), now)
    v.id = db.add_video(v)
    db.set_moment_status(m.id, "rendered")
    log.info("rendered %s (safe=%s)", out, v.safe)
    return v


async def render_moment(m: Moment, settings: Settings, db: Db,
                        download: Callable[[str, Path], Path] = ytdlp_download,
                        transcriber: Callable[[Path], list[Word]] = transcribe,
                        now: Callable[[], datetime] = utcnow) -> Video | None:
    work = settings.data_dir / "tmp" / f"moment{m.id}"
    try:
        try:
            src = await asyncio.to_thread(download, m.clip_url, work)
        except Exception as e:
            log.warning("download failed for %s: %s", m.clip_url, e)
            db.set_moment_status(m.id, "skipped")
            return None
        try:
            return await asyncio.to_thread(_render_sync, m, settings, db, src, work, transcriber, now())
        except subprocess.CalledProcessError as e:
            db.set_moment_status(m.id, "skipped")
            raise RuntimeError(f"ffmpeg failed: {(e.stderr or b'')[-800:]!r}") from e
    finally:
        shutil.rmtree(work, ignore_errors=True)
