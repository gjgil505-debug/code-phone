"""Decide when each platform posts, and what."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from clipbot.config import PLATFORMS, Settings
from clipbot.db import Db, Post, Video
from clipbot.publish.base import AuthError, Publisher

log = logging.getLogger(__name__)
RETRY_BACKOFF = (5, 20, 60)


def _local(now: datetime, settings: Settings) -> datetime:
    return now.astimezone(ZoneInfo(settings.timezone)) if settings.timezone else now.astimezone()


def in_quiet_hours(now: datetime, settings: Settings) -> bool:
    if not settings.quiet_hours:
        return False
    start_s, end_s = settings.quiet_hours.split("-")
    start, end = time.fromisoformat(start_s.strip()), time.fromisoformat(end_s.strip())
    t = _local(now, settings).time()
    return start <= t < end if start <= end else (t >= start or t < end)


def due_platforms(db: Db, settings: Settings, now: datetime) -> list[str]:
    if in_quiet_hours(now, settings):
        return []
    due = []
    for p in PLATFORMS:
        budget = settings.budgets.get(p, 0)
        if not settings.enabled.get(p) or budget <= 0 or db.get_state(f"disabled:{p}"):
            continue
        ok = [x for x in db.posts_since(p, now - timedelta(hours=24)) if x.status == "ok"]
        if len(ok) >= budget:
            continue
        if ok and now - max(x.created_at for x in ok) < timedelta(hours=24) / budget:
            continue
        due.append(p)
    return due


def choose_video(db: Db, platform: str, settings: Settings, now: datetime) -> Video | None:
    posted = db.posted_video_ids(platform)
    candidates = [v for v in db.videos_since(now - timedelta(hours=settings.freshness_hours))
                  if v.safe and v.id not in posted and Path(v.path).exists() and Path(v.meta_path).exists()]
    return max(candidates, key=lambda v: v.score, default=None)


async def _publish_with_retry(pub: Publisher, v: Video, meta: dict,
                              sleep: Callable[[float], Awaitable[None]]):
    for attempt in range(len(RETRY_BACKOFF) + 1):
        try:
            return await pub.publish(Path(v.path), meta)
        except AuthError:
            raise
        except Exception as e:
            if attempt == len(RETRY_BACKOFF):
                raise
            log.warning("%s upload failed (%s); retrying in %ss", pub.name, e, RETRY_BACKOFF[attempt])
            await sleep(RETRY_BACKOFF[attempt])


async def publish_once(db: Db, settings: Settings, publishers: dict[str, Publisher], now: datetime,
                       sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                       on_error: Callable[[str], None] | None = None) -> None:
    for platform in due_platforms(db, settings, now):
        pub = publishers.get(platform)
        v = choose_video(db, platform, settings, now) if pub else None
        if v is None:
            continue
        meta = json.loads(Path(v.meta_path).read_text())
        try:
            res = await _publish_with_retry(pub, v, meta, sleep)
        except AuthError as e:
            db.set_state(f"disabled:{platform}", f"{now.isoformat()} {e}")
            msg = f"{platform} login problem, posting paused: {e}. Run `clipbot auth {platform}`."
            log.error(msg)
            on_error and on_error(msg)
            continue
        except Exception as e:
            db.add_post(Post(platform, v.id, None, None, "failed", now, str(e)[:500]))
            msg = f"{platform} upload failed after retries: {e}"
            log.error(msg)
            on_error and on_error(msg)
            continue
        db.add_post(Post(platform, v.id, res.remote_id, res.url, "ok", now, None))
        log.info("posted video %s to %s: %s", v.id, platform, res.url or res.remote_id)
