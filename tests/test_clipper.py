from datetime import datetime, timedelta, timezone

import pytest

from clipbot.clipper import Clipper
from clipbot.config import Settings
from clipbot.db import Db, Moment
from clipbot.hype import Trigger
from clipbot.twitch.api import ClipInfo, StreamInfo, TwitchAuthError

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
STREAM = StreamInfo("42", "streamer", "StreamerName", 50000)
TRIG = Trigger("streamer", 5.5, "funny", 0.0, ["KEKW", "LUL"])


class FakeApi:
    def __init__(self, clip_id="C1", info=ClipInfo("C1", "https://clips.twitch.tv/C1", 30.0), exc=None):
        self.clip_id, self.info, self.exc = clip_id, info, exc
        self.created = []

    async def create_clip(self, bid):
        if self.exc:
            raise self.exc
        self.created.append(bid)
        return self.clip_id

    async def wait_clip(self, clip_id, timeout_s=20):
        return self.info


def _clipper(tmp_path, api, settings=Settings()):
    db = Db(tmp_path / "x.db")
    return Clipper(api, db, settings, now=lambda: NOW), db


async def test_ready_moment_stored(tmp_path):
    c, db = _clipper(tmp_path, FakeApi())
    m = await c.handle(TRIG, STREAM)
    assert m.status == "ready" and m.clip_url == "https://clips.twitch.tv/C1"
    got = db.get_moment(m.id)
    assert (got.channel, got.display_name, got.trigger_type, got.score, got.status) == \
        ("streamer", "StreamerName", "funny", 5.5, "ready")
    assert got.chat_snippet == ["KEKW", "LUL"]


async def test_clip_disabled_marks_unusable(tmp_path):
    c, db = _clipper(tmp_path, FakeApi(clip_id=None))
    m = await c.handle(TRIG, STREAM)
    assert db.get_moment(m.id).status == "unusable"


async def test_clip_never_appears_marks_unusable(tmp_path):
    c, db = _clipper(tmp_path, FakeApi(info=None))
    m = await c.handle(TRIG, STREAM)
    assert db.get_moment(m.id).status == "unusable"


async def test_auth_error_marks_unusable_and_raises(tmp_path):
    c, db = _clipper(tmp_path, FakeApi(exc=TwitchAuthError("x")))
    with pytest.raises(TwitchAuthError):
        await c.handle(TRIG, STREAM)
    assert [m.status for m in db.moments_since(NOW - timedelta(hours=1))] == ["unusable"]


async def test_hourly_cap_blocks_41st_clip(tmp_path):
    api = FakeApi()
    c, db = _clipper(tmp_path, api)
    for _ in range(40):
        assert await c.handle(TRIG, STREAM) is not None
    assert await c.handle(TRIG, STREAM) is None
    assert len(api.created) == 40
