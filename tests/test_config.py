from pathlib import Path

from clipbot.config import load_settings


def test_defaults_match_spec():
    s = load_settings(None, {})
    assert s.top_n == 25
    assert s.render_interval_min == 10
    assert s.discovery_interval_min == 5
    assert s.hype_threshold == 3.0
    assert s.min_post_score == 3.5
    assert s.game_name == "Grand Theft Auto VI"
    assert s.budgets == {"youtube": 6, "tiktok": 10, "instagram": 20}
    assert s.enabled and all(not v for v in s.enabled.values())
    assert s.quiet_hours is None
    assert s.keep_days == 7
    assert s.freshness_hours == 6


def test_yaml_overrides(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("top_n: 5\nenabled:\n  youtube: true\nbudgets:\n  tiktok: 3\n")
    s = load_settings(p, {})
    assert s.top_n == 5
    assert s.enabled["youtube"] is True
    assert s.enabled["tiktok"] is False
    assert s.budgets == {"youtube": 6, "tiktok": 3, "instagram": 20}


def test_env_secrets():
    s = load_settings(None, {"TWITCH_CLIENT_ID": "x", "TWITCH_CLIENT_SECRET": "y"})
    assert s.twitch_client_id == "x"
    assert s.twitch_client_secret == "y"


def test_facecam_tuple(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("facecams:\n  somestreamer: [1500, 40, 380, 220]\n")
    s = load_settings(p, {})
    assert s.facecams["somestreamer"] == (1500, 40, 380, 220)
