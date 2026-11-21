"""Pick the best moment of each render window."""
from __future__ import annotations

from datetime import datetime, timedelta

from clipbot.config import Settings
from clipbot.db import Db, Moment


def pick_winner(db: Db, settings: Settings, now: datetime) -> Moment | None:
    moments = db.ready_moments(now - timedelta(minutes=settings.render_interval_min))
    if not moments:
        return None
    best = max(moments, key=lambda m: m.score)
    winner = best if best.score >= settings.min_post_score else None
    for m in moments:
        if m is not winner:
            db.set_moment_status(m.id, "skipped")
    return winner
