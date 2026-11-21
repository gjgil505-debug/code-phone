from datetime import datetime, timedelta, timezone

from clipbot.config import Settings
from clipbot.db import Db, Moment
from clipbot.scheduler import pick_winner

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def _add(db, score, ago_min=1, status="ready"):
    return db.add_moment(Moment(None, "s", "S", "hype", score, NOW - timedelta(minutes=ago_min),
                                "c", "u", status, []))


def test_pick_highest_in_window(tmp_path):
    db = Db(tmp_path / "x.db")
    _add(db, 4.0)
    best = _add(db, 7.0)
    other = _add(db, 5.0)
    _add(db, 9.0, status="unusable")
    w = pick_winner(db, Settings(), NOW)
    assert w.id == best
    assert db.get_moment(other).status == "skipped"


def test_ignores_older_than_window(tmp_path):
    db = Db(tmp_path / "x.db")
    _add(db, 9.0, ago_min=11)
    assert pick_winner(db, Settings(), NOW) is None


def test_below_min_score_returns_none_and_skips(tmp_path):
    db = Db(tmp_path / "x.db")
    mid = _add(db, 3.2)
    assert pick_winner(db, Settings(), NOW) is None
    assert db.get_moment(mid).status == "skipped"


def test_empty_window_returns_none(tmp_path):
    assert pick_winner(Db(tmp_path / "x.db"), Settings(), NOW) is None
