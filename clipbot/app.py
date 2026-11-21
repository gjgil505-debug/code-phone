"""Main runner: wires discovery, chat, clipping, rendering and posting together."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

import httpx

from clipbot.clipper import Clipper
from clipbot.config import PLATFORMS, Settings
from clipbot.db import Db
from clipbot.housekeeping import cleanup
from clipbot.hype import ChatMessage, HypeDetector, Trigger
from clipbot.oauth import TokenStore
from clipbot.publish.instagram import InstagramPublisher
from clipbot.publish.planner import in_quiet_hours, publish_once
from clipbot.publish.tiktok import TikTokPublisher
from clipbot.publish.youtube import YouTubePublisher
from clipbot.render.pipeline import render_moment
from clipbot.scheduler import pick_winner
from clipbot.twitch.api import StreamInfo, TwitchApi
from clipbot.twitch.chat import ChatListener

log = logging.getLogger("clipbot")
MAX_ERRORS = 20


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_error(db: Db, msg: str, now: datetime | None = None) -> None:
    errs = json.loads(db.get_state("last_errors") or "[]")
    errs.append(f"{(now or utcnow()).strftime('%Y-%m-%d %H:%M')} {msg}")
    db.set_state("last_errors", json.dumps(errs[-MAX_ERRORS:]))


async def every(name: str, interval_s: float, body: Callable[[], Awaitable[None]], db: Db,
                sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, iterations: int | None = None) -> None:
    n = 0
    while iterations is None or n < iterations:
        n += 1
        try:
            await body()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("%s loop error", name)
            record_error(db, f"{name}: {e}")
        await sleep(interval_s)


def status_report(db: Db, s: Settings, now: datetime) -> str:
    watching = json.loads(db.get_state("watching") or "[]")
    lines = [f"Watching: {len(watching)} streams" + (f" ({', '.join(watching[:10])}"
                                                      f"{', ...' if len(watching) > 10 else ''})" if watching else "")]
    counts: dict[str, int] = {}
    for m in db.moments_since(now - timedelta(hours=1)):
        counts[m.status] = counts.get(m.status, 0) + 1
    lines.append("Hype moments in the last hour: " +
                 (", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "none"))
    videos = db.videos_since(now - timedelta(hours=24))
    lines.append(f"Videos made in the last 24h: {len(videos)} ({sum(not v.safe for v in videos)} held back by "
                 f"the word filter)")
    lines.append("Posting:" + (" (quiet hours now)" if in_quiet_hours(now, s) else ""))
    for p in PLATFORMS:
        disabled = db.get_state(f"disabled:{p}")
        if not s.enabled.get(p):
            lines.append(f"  {p}: off")
        elif disabled:
            lines.append(f"  {p}: PAUSED - {disabled} (fix with `clipbot auth {p}`)")
        else:
            ok = [x for x in db.posts_since(p, now - timedelta(hours=24)) if x.status == "ok"]
            failed = [x for x in db.posts_since(p, now - timedelta(hours=24)) if x.status == "failed"]
            lines.append(f"  {p}: posted {len(ok)}/{s.budgets.get(p, 0)} in the last 24h"
                         + (f", {len(failed)} failed" if failed else ""))
    errs = json.loads(db.get_state("last_errors") or "[]")[-5:]
    lines.append("Recent problems:" + ("" if errs else " none"))
    lines += [f"  {e}" for e in errs]
    return "\n".join(lines)


async def run(s: Settings) -> None:
    db = Db(s.db_path)
    tokens = TokenStore(s.tokens_path)
    client = httpx.AsyncClient(timeout=httpx.Timeout(60, read=600))
    api = TwitchApi(s, tokens, client)
    detector = HypeDetector(s)
    clipper = Clipper(api, db, s)
    streams: dict[str, StreamInfo] = {}
    pending: set[asyncio.Task] = set()
    publishers = {"youtube": YouTubePublisher(s, tokens, client), "tiktok": TikTokPublisher(s, tokens, client),
                  "instagram": InstagramPublisher(s, tokens, client)}

    def spawn_clip(t: Trigger) -> None:
        stream = streams.get(t.channel)
        if not stream:
            return

        async def go():
            try:
                await clipper.handle(t, stream)
            except Exception as e:
                log.error("clip error on %s: %s", t.channel, e)
                record_error(db, f"clip: {e}")

        task = asyncio.create_task(go())
        pending.add(task)
        task.add_done_callback(pending.discard)

    def on_message(msg: ChatMessage) -> None:
        if msg.channel in streams:
            t = detector.feed(msg)
            if t:
                spawn_clip(t)

    async def discover():
        found = await api.top_streams()
        streams.clear()
        streams.update({x.login: x for x in found})
        for ch in list(detector.channels):
            if ch not in streams:
                detector.forget(ch)
        db.set_state("watching", json.dumps(list(streams)))
        log.info("watching %d GTA 6 streams", len(streams))

    async def tick():
        for t in detector.tick(time.time()):
            spawn_clip(t)

    async def render():
        winner = pick_winner(db, s, utcnow())
        if winner:
            await render_moment(winner, s, db)

    async def publish():
        await publish_once(db, s, publishers, utcnow(), on_error=lambda m: record_error(db, m))

    async def housekeeping():
        cleanup(s, utcnow())

    listener = ChatListener(lambda: set(streams), on_message)
    log.info("clipbot starting (posting enabled: %s)", [p for p, on in s.enabled.items() if on] or "none")
    try:
        await asyncio.gather(
            every("discovery", s.discovery_interval_min * 60, discover, db),
            listener.run(),
            every("tick", 1, tick, db),
            every("render", s.render_interval_min * 60, render, db),
            every("publish", 60, publish, db),
            every("housekeeping", 3600, housekeeping, db),
        )
    finally:
        await client.aclose()
