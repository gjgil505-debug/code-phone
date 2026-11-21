"""Disk cleanup so an always-on bot doesn't fill the drive."""
from __future__ import annotations

import shutil
from datetime import date, datetime, timedelta

from clipbot.config import Settings

TMP_MAX_AGE_S = 3600


def cleanup(settings: Settings, now: datetime) -> None:
    cutoff = now.date() - timedelta(days=settings.keep_days)
    if settings.output_dir.exists():
        for d in settings.output_dir.iterdir():
            try:
                day = date.fromisoformat(d.name)
            except ValueError:
                continue
            if d.is_dir() and day < cutoff:
                shutil.rmtree(d, ignore_errors=True)
    tmp = settings.data_dir / "tmp"
    if tmp.exists():
        for p in tmp.iterdir():
            if now.timestamp() - p.stat().st_mtime > TMP_MAX_AGE_S:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
