"""Posting looks like a person: fewer posts, random times, waking hours only, never two platforms at once."""
import json
import random
from datetime import datetime, timedelta, timezone

from clipbot.config import Settings
from clipbot.db import Db, Post
from clipbot.publish.planner import daily_plan, due_platforms, make_plan

UTC = timezone.utc
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
ON = {"youtube": True, "tiktok": True, "instagram": False}


def S(**kw):
    kw.setdefault("enabled", dict(ON))
    return Settings(timezone="UTC", **kw)


def _plan(db, platform, *hhmm):
    times = [NOW.replace(hour=int(t[:2]), minute=int(t[3:])).isoformat() for t in hhmm]
    db.set_state(f"plan:{platform}:2026-11-21", json.dumps(times))


def _post(db, platform, when, status="ok"):
    db.add_post(Post(platform, 1, "r", "u", status, when, None))


def test_defaults_post_well_under_platform_limits():
    s = Settings()
    assert s.daily_posts == {"youtube": (2, 4), "tiktok": (3, 6), "instagram": (2, 5)}
    for p, (lo, hi) in s.daily_posts.items():
        assert hi < s.budgets[p]
    assert s.active_hours == "10:00-23:00"
    assert (s.min_gap_min, s.stagger_min, s.retry_after_fail_min) == (45, 10, 30)


def test_make_plan_random_times_inside_window_with_gaps():
    start, end = NOW.replace(hour=10), NOW.replace(hour=23)
    seen = set()
    for seed in range(50):
        times = make_plan(random.Random(seed), 5, start, end, timedelta(minutes=45))
        assert len(times) == 5 and times == sorted(times)
        assert all(start <= t <= end for t in times)
        assert all(b - a >= timedelta(minutes=45) for a, b in zip(times, times[1:]))
        seen.add(times[0])
    assert len(seen) > 40  # not a fixed schedule


def test_make_plan_shrinks_when_window_too_small():
    start = NOW.replace(hour=22)
    times = make_plan(random.Random(1), 4, start, start + timedelta(hours=1), timedelta(minutes=45))
    assert 1 <= len(times) <= 2


def test_make_plan_empty_when_window_over():
    assert make_plan(random.Random(1), 3, NOW, NOW - timedelta(hours=1), timedelta(minutes=45)) == []


def test_daily_plan_count_in_range_and_survives_restart(tmp_path):
    db = Db(tmp_path / "x.db")
    counts = set()
    for seed in range(30):
        db2 = Db(tmp_path / f"d{seed}.db")
        plan = daily_plan(db2, S(), "youtube", NOW.replace(hour=0, minute=5), random.Random(seed))
        assert 2 <= len(plan) <= 4
        counts.add(len(plan))
    assert len(counts) > 1  # different number of posts on different days
    first = daily_plan(db, S(), "youtube", NOW, random.Random(1))
    assert daily_plan(Db(tmp_path / "x.db"), S(), "youtube", NOW, random.Random(999)) == first


def test_daily_plan_made_mid_day_uses_remaining_window(tmp_path):
    late = NOW.replace(hour=20)
    plan = daily_plan(Db(tmp_path / "x.db"), S(), "tiktok", late, random.Random(3))
    assert plan and all(late <= t <= NOW.replace(hour=23) for t in plan)


def test_daily_plan_capped_by_budget(tmp_path):
    s = S(daily_posts={"youtube": (5, 8)}, budgets={"youtube": 3})
    for seed in range(10):
        assert len(daily_plan(Db(tmp_path / f"{seed}.db"), s, "youtube", NOW.replace(hour=0), random.Random(seed))) <= 3


def test_not_due_before_first_planned_time(tmp_path):
    db = Db(tmp_path / "x.db")
    _plan(db, "youtube", "13:00", "15:00")
    _plan(db, "tiktok", "14:00")
    assert due_platforms(db, S(), NOW) == []


def test_due_once_planned_time_passes(tmp_path):
    db = Db(tmp_path / "x.db")
    _plan(db, "youtube", "11:30", "15:00")
    _plan(db, "tiktok", "14:00")
    assert due_platforms(db, S(), NOW) == ["youtube"]


def test_done_for_the_day_after_all_planned_posts(tmp_path):
    db = Db(tmp_path / "x.db")
    _plan(db, "youtube", "10:30")
    _plan(db, "tiktok", "14:00")
    _post(db, "youtube", NOW.replace(hour=10, minute=31))
    assert due_platforms(db, S(), NOW) == []


def test_yesterdays_posts_do_not_use_up_today(tmp_path):
    db = Db(tmp_path / "x.db")
    _plan(db, "youtube", "10:30")
    _plan(db, "tiktok", "14:00")
    _post(db, "youtube", NOW - timedelta(hours=13))  # 23:00 yesterday
    assert due_platforms(db, S(), NOW) == ["youtube"]


def test_only_one_platform_at_a_time_and_stagger(tmp_path):
    db = Db(tmp_path / "x.db")
    _plan(db, "youtube", "11:00")
    _plan(db, "tiktok", "11:30")
    assert due_platforms(db, S(), NOW) == ["youtube"]  # earliest overdue goes first, alone
    _post(db, "youtube", NOW - timedelta(minutes=5))
    assert due_platforms(db, S(), NOW) == []  # tiktok waits 10 min after any post
    assert due_platforms(db, S(), NOW + timedelta(minutes=6)) == ["tiktok"]


def test_outside_active_hours_not_due(tmp_path):
    db = Db(tmp_path / "x.db")
    early = NOW.replace(hour=8)
    db.set_state("plan:youtube:2026-11-21", json.dumps([NOW.replace(hour=7).isoformat()]))
    db.set_state("plan:tiktok:2026-11-21", json.dumps([]))
    assert due_platforms(db, S(), early) == []


def test_quiet_hours_still_respected(tmp_path):
    db = Db(tmp_path / "x.db")
    _plan(db, "youtube", "11:00")
    _plan(db, "tiktok", "16:00")
    assert due_platforms(db, S(quiet_hours="11:30-12:30"), NOW) == []


def test_failure_waits_30_minutes(tmp_path):
    db = Db(tmp_path / "x.db")
    _plan(db, "youtube", "11:00")
    _plan(db, "tiktok", "16:00")
    _post(db, "youtube", NOW - timedelta(minutes=10), status="failed")
    assert due_platforms(db, S(), NOW) == []
    assert due_platforms(db, S(), NOW + timedelta(minutes=21)) == ["youtube"]


def test_same_platform_min_gap_after_late_post(tmp_path):
    db = Db(tmp_path / "x.db")
    _plan(db, "youtube", "10:30", "11:20")
    _plan(db, "tiktok", "16:00")
    _post(db, "youtube", NOW - timedelta(minutes=20))  # first post went out late
    assert due_platforms(db, S(), NOW) == []
    assert due_platforms(db, S(), NOW + timedelta(minutes=26)) == ["youtube"]


def test_rolling_24h_cap_still_enforced(tmp_path):
    db = Db(tmp_path / "x.db")
    _plan(db, "youtube", "11:00")
    _plan(db, "tiktok", "16:00")
    _post(db, "youtube", NOW - timedelta(hours=14))
    assert due_platforms(db, S(budgets={"youtube": 1, "tiktok": 10, "instagram": 20}), NOW) == []


def test_disabled_platform_not_due(tmp_path):
    db = Db(tmp_path / "x.db")
    _plan(db, "youtube", "11:00")
    _plan(db, "tiktok", "11:10")
    db.set_state("disabled:youtube", "login expired")
    assert due_platforms(db, S(), NOW) == ["tiktok"]
