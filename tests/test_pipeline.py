import json
import shutil
from datetime import datetime, timezone

import pytest

from clipbot.config import Settings
from clipbot.db import Db, Moment
from clipbot.render.captions import Word
from clipbot.render.peak import probe
from clipbot.render.pipeline import render_moment

NOW = datetime(2026, 11, 21, 12, 34, tzinfo=timezone.utc)


def _setup(tmp_path, clip):
    s = Settings(data_dir=tmp_path / "data", output_dir=tmp_path / "out")
    db = Db(s.db_path)
    m = Moment(None, "streamer", "StreamerName", "funny", 5.0, NOW, "C1", "https://clips.twitch.tv/C1", "ready", [])
    m.id = db.add_moment(m)
    downloaded = []

    def download(url, dest):
        dest.mkdir(parents=True, exist_ok=True)
        p = dest / "src.mp4"
        shutil.copy(clip, p)
        downloaded.append(p)
        return p

    return s, db, m, download, downloaded


@pytest.mark.slow
async def test_render_end_to_end(tmp_path, make_clip):
    s, db, m, download, downloaded = _setup(tmp_path, make_clip(seconds=20, loud_at=14.0))
    words = lambda p: [Word(2.0, 2.4, "no"), Word(2.4, 2.8, "way"), Word(2.8, 3.2, "bro")]
    v = await render_moment(m, s, db, download=download, transcriber=words, now=lambda: NOW)
    info = probe(v.path)
    assert (info.width, info.height) == (1080, 1920)
    assert abs(info.duration - (20 + 1.5 + 0.15)) <= 0.5
    assert v.path.endswith("2026-11-21/1234_streamer.mp4")
    meta = json.loads(open(v.meta_path).read())
    assert "@StreamerName" in meta["description"] and "twitch.tv/streamer" in meta["description"]
    assert meta["hashtags"][:2] == ["#GTA6", "#GTAVI"] and "#streamer" in meta["hashtags"]
    assert meta["display_name"] == "StreamerName" and meta["hook_text"]
    assert v.safe is True and db.get_moment(m.id).status == "rendered"
    assert not downloaded[0].exists()
    assert db.videos_since(NOW)[0].id == v.id


@pytest.mark.slow
async def test_render_empty_transcript_renders(tmp_path, make_clip):
    s, db, m, download, _ = _setup(tmp_path, make_clip(seconds=6, loud_at=2.0, audio=False))
    v = await render_moment(m, s, db, download=download, transcriber=lambda p: [], now=lambda: NOW)
    assert v is not None and v.safe is True


@pytest.mark.slow
async def test_render_unsafe_transcript_marks_unsafe(tmp_path, make_clip):
    s, db, m, download, _ = _setup(tmp_path, make_clip(seconds=5, loud_at=1.0))
    v = await render_moment(m, s, db, download=download,
                            transcriber=lambda p: [Word(0.5, 1.0, "retard")], now=lambda: NOW)
    assert v.safe is False


async def test_render_too_short_skips(tmp_path, make_clip):
    s, db, m, download, downloaded = _setup(tmp_path, make_clip(seconds=2, loud_at=0.5))
    assert await render_moment(m, s, db, download=download, transcriber=lambda p: [], now=lambda: NOW) is None
    assert db.get_moment(m.id).status == "skipped"
    assert not downloaded[0].exists()


async def test_render_download_failure_skips(tmp_path, make_clip):
    s, db, m, _, _ = _setup(tmp_path, make_clip(seconds=2))

    def broken(url, dest):
        raise RuntimeError("yt-dlp failed")

    assert await render_moment(m, s, db, download=broken, transcriber=lambda p: [], now=lambda: NOW) is None
    assert db.get_moment(m.id).status == "skipped"
