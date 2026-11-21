import os
import time
from datetime import datetime, timezone

from clipbot.config import Settings
from clipbot.housekeeping import cleanup

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def test_cleanup_removes_old_days_only(tmp_path):
    s = Settings(data_dir=tmp_path / "data", output_dir=tmp_path / "out", keep_days=7)
    for d in ("2026-11-10", "2026-11-14", "2026-11-15", "2026-11-21", "notadate"):
        (s.output_dir / d).mkdir(parents=True)
        (s.output_dir / d / "x.mp4").write_bytes(b"x")
    cleanup(s, NOW)
    assert sorted(p.name for p in s.output_dir.iterdir()) == ["2026-11-14", "2026-11-15", "2026-11-21", "notadate"]


def test_cleanup_removes_stale_tmp(tmp_path):
    s = Settings(data_dir=tmp_path / "data", output_dir=tmp_path / "out")
    old, new = s.data_dir / "tmp" / "old", s.data_dir / "tmp" / "new"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    t = NOW.timestamp() - 2 * 3600
    os.utime(old, (t, t))
    os.utime(new, (NOW.timestamp(), NOW.timestamp()))
    cleanup(s, NOW)
    assert not old.exists() and new.exists()
