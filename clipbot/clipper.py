"""Turn a hype trigger into a Twitch clip and a stored Moment."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from clipbot.config import Settings
from clipbot.db import Db, Moment
from clipbot.hype import Trigger
from clipbot.twitch.api import StreamInfo, TwitchApi, TwitchAuthError

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Clipper:
    def __init__(self, api: TwitchApi, db: Db, settings: Settings, now: Callable[[], datetime] = utcnow):
        self.api, self.db, self.s, self.now = api, db, settings, now

    async def handle(self, trigger: Trigger, stream: StreamInfo) -> Moment | None:
        now = self.now()
        if len(self.db.moments_since(now - timedelta(hours=1))) >= self.s.max_clips_per_hour:
            log.info("hourly clip cap reached; ignoring spike on %s", stream.login)
            return None
        m = Moment(None, stream.login, stream.display_name, trigger.trigger_type, trigger.score, now,
                   None, None, "pending", list(trigger.snippet))
        m.id = self.db.add_moment(m)
        try:
            m.clip_id = await self.api.create_clip(stream.user_id)
            info = await self.api.wait_clip(m.clip_id) if m.clip_id else None
        except TwitchAuthError:
            m.status = "unusable"
            self.db.update_moment(m)
            raise
        except Exception as e:
            log.warning("clip failed for %s: %s", stream.login, e)
            info = None
        if info is None:
            m.status = "unusable"
        else:
            m.clip_url, m.status = info.url, "ready"
            log.info("clipped %s (%s, score %.1f): %s", stream.login, trigger.trigger_type, trigger.score, info.url)
        self.db.update_moment(m)
        return m
