import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from clipbot.config import Settings
from clipbot.db import Db, Post, Video
from clipbot.publish.base import AuthError, PostResult
from clipbot.publish.planner import choose_video, due_platforms, publish_once

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
ON = {"youtube": True, "tiktok": True, "instagram": False}


def S(**kw):
    kw.setdefault("enabled", dict(ON))
    return Settings(timezone="UTC", **kw)


def _video(db, tmp_path, score=5.0, ago_h=1.0, safe=True):
    p = tmp_path / f"v{score}-{ago_h}-{safe}.mp4"
    p.write_bytes(b"x")
    meta = p.with_suffix(".json")
    meta.write_text(json.dumps({"title": "T", "description": "@StreamerName", "hashtags": ["#GTA6"],
                                "display_name": "StreamerName"}))
    return db.add_video(Video(None, 1, str(p), str(meta), score, "h", safe, NOW - timedelta(hours=ago_h)))


def _due_now(db, *platforms):
    for p in platforms:
        db.set_state(f"plan:{p}:2026-11-21", json.dumps([(NOW - timedelta(minutes=5)).isoformat()]))


def _post(db, platform, vid, ago_h, status="ok"):
    db.add_post(Post(platform, vid, "r", "u", status, NOW - timedelta(hours=ago_h), None))


def test_choose_skips_unsafe_stale_missing_and_already_posted(tmp_path):
    db = Db(tmp_path / "x.db")
    posted = _video(db, tmp_path, score=9)
    _video(db, tmp_path, score=8, safe=False)
    _video(db, tmp_path, score=7, ago_h=7)
    gone = _video(db, tmp_path, score=6.5)
    Path(db.videos_since(NOW - timedelta(days=1))[-1].path).unlink()
    good = _video(db, tmp_path, score=6)
    _video(db, tmp_path, score=5)
    _post(db, "youtube", posted, 1)
    assert gone != good
    assert choose_video(db, "youtube", S(), NOW).id == good
    assert choose_video(db, "tiktok", S(), NOW).id == posted


def test_restart_does_not_double_post(tmp_path):
    db = Db(tmp_path / "x.db")
    vid = _video(db, tmp_path)
    _post(db, "youtube", vid, 0.1)
    assert choose_video(Db(tmp_path / "x.db"), "youtube", S(), NOW) is None


class Pub:
    def __init__(self, name, results):
        self.name, self.results, self.calls = name, list(results), []

    async def publish(self, path, meta):
        self.calls.append((path, meta))
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


async def test_publish_once_records_ok_post_with_meta(tmp_path):
    db = Db(tmp_path / "x.db")
    vid = _video(db, tmp_path)
    _due_now(db, "youtube")
    yt = Pub("youtube", [PostResult("abc", "https://youtube.com/shorts/abc")])
    await publish_once(db, S(enabled={"youtube": True}), {"youtube": yt}, NOW)
    assert yt.calls[0][1]["description"] == "@StreamerName"
    posts = db.posts_since("youtube", NOW - timedelta(hours=1))
    assert [(p.video_id, p.status, p.url) for p in posts] == [(vid, "ok", "https://youtube.com/shorts/abc")]


async def test_auth_error_disables_only_that_platform(tmp_path):
    db = Db(tmp_path / "x.db")
    _video(db, tmp_path)
    _due_now(db, "youtube")
    db.set_state("plan:tiktok:2026-11-21", json.dumps([(NOW - timedelta(minutes=1)).isoformat()]))
    errors = []
    yt = Pub("youtube", [AuthError("invalid_grant")])
    tt = Pub("tiktok", [PostResult("p1", None)])
    await publish_once(db, S(), {"youtube": yt, "tiktok": tt}, NOW, on_error=errors.append)
    await publish_once(db, S(), {"youtube": yt, "tiktok": tt}, NOW, on_error=errors.append)
    assert "invalid_grant" in db.get_state("disabled:youtube")
    assert [p.status for p in db.posts_since("tiktok", NOW - timedelta(hours=1))] == ["ok"]
    assert any("youtube" in e for e in errors)


async def test_transient_error_retries_then_records_failed(tmp_path):
    db = Db(tmp_path / "x.db")
    vid = _video(db, tmp_path)
    _due_now(db, "youtube")
    sleeps = []

    async def sleep(s):
        sleeps.append(s)

    yt = Pub("youtube", [RuntimeError("503")] * 4)
    await publish_once(db, S(enabled={"youtube": True}), {"youtube": yt}, NOW, sleep=sleep)
    assert sleeps == [5, 20, 60] and len(yt.calls) == 4
    posts = db.posts_since("youtube", NOW - timedelta(hours=1))
    assert [(p.video_id, p.status) for p in posts] == [(vid, "failed")] and "503" in posts[0].error


async def test_transient_error_then_success(tmp_path):
    db = Db(tmp_path / "x.db")
    _video(db, tmp_path)
    _due_now(db, "youtube")

    async def sleep(s):
        pass

    yt = Pub("youtube", [RuntimeError("503"), PostResult("a", None)])
    await publish_once(db, S(enabled={"youtube": True}), {"youtube": yt}, NOW, sleep=sleep)
    assert [p.status for p in db.posts_since("youtube", NOW - timedelta(hours=1))] == ["ok"]


async def test_nothing_to_post_does_nothing(tmp_path):
    db = Db(tmp_path / "x.db")
    _due_now(db, "youtube")
    yt = Pub("youtube", [])
    await publish_once(db, S(enabled={"youtube": True}), {"youtube": yt}, NOW)
    assert yt.calls == []


def test_choose_never_posts_manual_test_renders(tmp_path):
    db = Db(tmp_path / "x.db")
    _video(db, tmp_path, score=0.0)  # `clipbot render` creates score-0 videos
    assert choose_video(db, "youtube", S(), NOW) is None
