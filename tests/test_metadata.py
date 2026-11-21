import random
from datetime import datetime, timezone

from clipbot.db import Moment
from clipbot.render.pipeline import _metadata, screen_name

M = Moment(1, "streamer", "StreamerName", "funny", 5.0, datetime(2026, 11, 21, tzinfo=timezone.utc), "C",
           "https://clips.twitch.tv/C", "ready", [])


def test_metadata_always_credits_and_tags_streamer():
    for seed in range(30):
        meta = _metadata(M, "NOBODY EXPECTED THIS", random.Random(seed))
        assert "@StreamerName" in meta["description"] and "twitch.tv/streamer" in meta["description"]
        assert "#GTA6" in meta["hashtags"] and "#streamer" in meta["hashtags"]
        assert 4 <= len(meta["hashtags"]) <= 6 and len(set(meta["hashtags"])) == len(meta["hashtags"])


def test_metadata_varies_between_posts():
    metas = [_metadata(M, "NOBODY EXPECTED THIS", random.Random(seed)) for seed in range(30)]
    assert len({m["description"].split("\n")[0] for m in metas}) >= 3
    assert len({tuple(m["hashtags"]) for m in metas}) >= 10


def test_title_case_keeps_apostrophes_right():
    assert _metadata(M, "I CAN'T STOP LAUGHING AT THIS", random.Random(1))["title"] == "I Can't Stop Laughing At This"


def test_description_links_original_clip():
    for seed in range(10):
        assert "https://clips.twitch.tv/C" in _metadata(M, "X", random.Random(seed))["description"]


def test_screen_name_falls_back_to_login_for_unsupported_scripts():
    def m(display, login):
        return Moment(1, login, display, "funny", 5.0, M.created_at, "C", "u", "ready", [])
    assert screen_name(m("사나이", "sanai")) == "sanai"
    assert screen_name(m("ZoëGamer", "zoegamer")) == "ZoëGamer"
    assert screen_name(m("StreamerName", "streamername")) == "StreamerName"
