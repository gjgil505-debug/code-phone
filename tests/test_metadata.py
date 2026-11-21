import random
from datetime import datetime, timezone

from clipbot.db import Moment
from clipbot.render.pipeline import _metadata

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
