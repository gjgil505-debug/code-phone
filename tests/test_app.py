import json
from datetime import datetime, timedelta, timezone

from clipbot.app import every, record_error, status_report
from clipbot.config import Settings
from clipbot.db import Db, Moment, Post

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


async def test_loop_survives_exception(tmp_path):
    db = Db(tmp_path / "x.db")
    calls = []

    async def body():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("kaboom")

    async def nosleep(_):
        pass

    await every("render", 600, body, db, sleep=nosleep, iterations=2)
    assert len(calls) == 2
    assert "kaboom" in json.loads(db.get_state("last_errors"))[-1]


def test_record_error_keeps_last_20(tmp_path):
    db = Db(tmp_path / "x.db")
    for i in range(25):
        record_error(db, f"e{i}", NOW)
    errs = json.loads(db.get_state("last_errors"))
    assert len(errs) == 20 and errs[-1].endswith("e24")


def test_status_shows_budget_and_disabled(tmp_path):
    s = Settings(enabled={"youtube": True, "tiktok": True, "instagram": False}, timezone="UTC")
    db = Db(tmp_path / "x.db")
    db.set_state("watching", json.dumps(["a", "b", "c"]))
    db.add_moment(Moment(None, "a", "A", "funny", 4, NOW - timedelta(minutes=5), "c", "u", "ready", []))
    db.add_post(Post("youtube", 1, "r", "u", "ok", NOW - timedelta(hours=1), None))
    db.set_state("disabled:tiktok", "2026-11-21 login expired")
    record_error(db, "tiktok login problem", NOW)
    out = status_report(db, s, NOW)
    assert "Watching: 3 streams" in out
    assert "ready: 1" in out
    assert "youtube: posted 1 of" in out and "planned today" in out
    assert "tiktok: PAUSED" in out and "login expired" in out
    assert "instagram: off" in out
    assert "tiktok login problem" in out
