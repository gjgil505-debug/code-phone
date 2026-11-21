"""Decide when each platform posts, and what."""
from __future__ import annotations

import asyncio
import json
import logging
import random
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


def _parse_window(spec: str, day_start: datetime) -> tuple[datetime, datetime]:
    a, b = (time.fromisoformat(x.strip()) for x in spec.split("-"))
    start = day_start.replace(hour=a.hour, minute=a.minute)
    end = day_start.replace(hour=b.hour, minute=b.minute)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def _day_window(now: datetime, s: Settings) -> tuple[datetime, datetime, datetime]:
    """(local midnight, active-window start, active-window end) for the local day containing `now`."""
    local = _local(now, s)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if not s.active_hours:
        return midnight, midnight, midnight + timedelta(days=1)
    start, end = _parse_window(s.active_hours, midnight)
    return midnight, start, end


def make_plan(rng: random.Random, n: int, start: datetime, end: datetime, gap: timedelta) -> list[datetime]:
    """`n` random times in [start, end], sorted, at least `gap` apart (fewer if they don't fit)."""
    span = (end - start).total_seconds()
    if n <= 0 or span < 0:
        return []
    n = min(n, int(span // gap.total_seconds()) + 1)
    slack = span - (n - 1) * gap.total_seconds()
    offsets = sorted(rng.uniform(0, slack) for _ in range(n))
    return [start + timedelta(seconds=o) + i * gap for i, o in enumerate(offsets)]


def daily_plan(db: Db, s: Settings, platform: str, now: datetime,
               rng: random.Random | None = None) -> list[datetime]:
    """Today's random posting times for a platform; made once per day and saved so restarts keep it."""
    midnight, start, end = _day_window(now, s)
    key = f"plan:{platform}:{midnight.date().isoformat()}"
    saved = db.get_state(key)
    if saved is not None:
        return [datetime.fromisoformat(t) for t in json.loads(saved)]
    rng = rng or random.Random()
    lo, hi = s.daily_posts.get(platform, (0, 0))
    hi = min(hi, s.budgets.get(platform, 0))
    n = rng.randint(min(lo, hi), hi) if hi > 0 else 0
    plan = make_plan(rng, n, max(start, _local(now, s)), end, timedelta(minutes=s.min_gap_min))
    db.set_state(key, json.dumps([t.isoformat() for t in plan]))
    return plan


def _platform_status(db: Db, s: Settings, p: str, now: datetime) -> tuple[list[datetime], int, datetime | None]:
    """(today's plan, ok posts made today, time of the next planned post)."""
    midnight, _, _ = _day_window(now, s)
    plan = daily_plan(db, s, p, now)
    done = sum(1 for x in db.posts_since(p, midnight) if x.status == "ok")
    return plan, done, plan[done] if done < len(plan) else None


def due_platforms(db: Db, settings: Settings, now: datetime) -> list[str]:
    """The one platform (if any) that should post right now. At most one, so posts never go out together."""
    s = settings
    if in_quiet_hours(now, s):
        return []
    _, start, end = _day_window(now, s)
    if not start <= _local(now, s) <= end:
        return []
    recent_any = any(x.status == "ok" for p in PLATFORMS
                     for x in db.posts_since(p, now - timedelta(minutes=s.stagger_min)))
    if recent_any:
        return []
    candidates = []
    for p in PLATFORMS:
        budget = s.budgets.get(p, 0)
        if not s.enabled.get(p) or budget <= 0 or db.get_state(f"disabled:{p}"):
            continue
        _, _, next_at = _platform_status(db, s, p, now)
        if next_at is None or next_at > now:
            continue
        last24 = db.posts_since(p, now - timedelta(hours=24))
        ok = [x for x in last24 if x.status == "ok"]
        if len(ok) >= budget:
            continue
        if ok and now - max(x.created_at for x in ok) < timedelta(minutes=s.min_gap_min):
            continue
        fails = [x.created_at for x in last24 if x.status == "failed"]
        if fails and now - max(fails) < timedelta(minutes=s.retry_after_fail_min):
            continue
        candidates.append((next_at, p))
    return [min(candidates)[1]] if candidates else []


def choose_video(db: Db, platform: str, settings: Settings, now: datetime) -> Video | None:
    posted = db.attempted_video_ids(platform)  # never resend: avoids poison videos and double posts
    candidates = [v for v in db.videos_since(now - timedelta(hours=settings.freshness_hours))
                  if v.safe and v.score >= settings.min_post_score and v.id not in posted
                  and Path(v.path).exists() and Path(v.meta_path).exists()]
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
