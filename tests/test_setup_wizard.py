import yaml

from clipbot.setup_wizard import enable_platforms, read_env, run_wizard, write_env


def test_write_env_merges_and_keeps_other_lines(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# comment\nTWITCH_CLIENT_ID=old\nOTHER=x\n")
    write_env(p, {"TWITCH_CLIENT_ID": "new", "GOOGLE_CLIENT_ID": "g"})
    text = p.read_text()
    assert "# comment" in text and "OTHER=x" in text
    assert read_env(p) == {"TWITCH_CLIENT_ID": "new", "OTHER": "x", "GOOGLE_CLIENT_ID": "g"}
    assert (p.stat().st_mode & 0o777) == 0o600


def test_enable_platforms_keeps_other_settings(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("top_n: 10\nenabled:\n  youtube: false\n")
    enable_platforms(p, {"youtube": True, "tiktok": False, "instagram": True})
    data = yaml.safe_load(p.read_text())
    assert data["top_n"] == 10
    assert data["enabled"] == {"youtube": True, "tiktok": False, "instagram": True}


def test_wizard_asks_keys_skips_blank_and_enables_chosen(tmp_path):
    env, cfg = tmp_path / ".env", tmp_path / "config.yaml"
    env.write_text("TWITCH_CLIENT_ID=keepme\n")
    answers = iter([
        "",            # TWITCH_CLIENT_ID: keep existing
        "tsecret",     # TWITCH_CLIENT_SECRET
        "y",           # set up YouTube?
        "gid", "gsec",
        "n",           # TikTok? no
        "y",           # Instagram?
        "mid", "msec",
    ])
    shown = []
    run_wizard(env, cfg, ask=lambda prompt: next(answers), say=shown.append)
    vals = read_env(env)
    assert vals["TWITCH_CLIENT_ID"] == "keepme" and vals["TWITCH_CLIENT_SECRET"] == "tsecret"
    assert vals["GOOGLE_CLIENT_ID"] == "gid" and vals["META_APP_SECRET"] == "msec"
    assert "TIKTOK_CLIENT_KEY" not in vals
    assert yaml.safe_load(cfg.read_text())["enabled"] == {"youtube": True, "tiktok": False, "instagram": True}
    out = "\n".join(shown)
    assert "clipbot auth twitch" in out and "clipbot auth youtube" in out and "clipbot auth instagram" in out
    assert "clipbot auth tiktok" not in out
