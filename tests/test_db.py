from datetime import datetime, timedelta, timezone

from clipbot.db import Db, Moment, Post, Video

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def _moment(**kw):
    base = dict(id=None, channel="streamer", display_name="Streamer", trigger_type="funny",
                score=4.2, created_at=NOW, clip_id="c1", clip_url="https://clips.twitch.tv/c1",
                status="ready", chat_snippet=["KEKW", "LUL"])
    base.update(kw)
    return Moment(**base)


def test_moment_roundtrip(tmp_path):
    db = Db(tmp_path / "x.db")
    mid = db.add_moment(_moment())
    got = db.ready_moments(NOW - timedelta(minutes=1))
    assert len(got) == 1
    assert got[0] == _moment(id=mid)


def test_ready_moments_excludes_other_status_and_old(tmp_path):
    db = Db(tmp_path / "x.db")
    db.add_moment(_moment(status="pending"))
    db.add_moment(_moment(created_at=NOW - timedelta(hours=1)))
    assert db.ready_moments(NOW - timedelta(minutes=10)) == []


def test_set_moment_status(tmp_path):
    db = Db(tmp_path / "x.db")
    mid = db.add_moment(_moment())
    db.set_moment_status(mid, "rendered")
    assert db.ready_moments(NOW - timedelta(minutes=1)) == []
    assert db.get_moment(mid).status == "rendered"


def test_video_roundtrip(tmp_path):
    db = Db(tmp_path / "x.db")
    v = Video(id=None, moment_id=1, path="o.mp4", meta_path="o.json", score=4.0,
              hook_id="funny-1", safe=True, created_at=NOW)
    vid = db.add_video(v)
    got = db.videos_since(NOW - timedelta(minutes=1))
    assert got[0].id == vid and got[0].safe is True and got[0].hook_id == "funny-1"
    assert db.recent_hook_ids(10) == ["funny-1"]


def test_posts_since_filters_platform_and_time(tmp_path):
    db = Db(tmp_path / "x.db")
    db.add_post(Post("youtube", 1, "r1", "u", "ok", NOW - timedelta(hours=1), None))
    db.add_post(Post("youtube", 2, "r2", "u", "ok", NOW - timedelta(hours=30), None))
    db.add_post(Post("tiktok", 3, "r3", "u", "ok", NOW, None))
    got = db.posts_since("youtube", NOW - timedelta(hours=24))
    assert [p.video_id for p in got] == [1]
    assert db.posted_video_ids("youtube") == {1, 2}


def test_state_kv(tmp_path):
    db = Db(tmp_path / "x.db")
    assert db.get_state("k") is None
    db.set_state("k", "v")
    db.set_state("k", "v2")
    assert db.get_state("k") == "v2"
    db.delete_state("k")
    assert db.get_state("k") is None
