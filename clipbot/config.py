"""Settings: defaults from the design spec, overridden by config.yaml and .env."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping

import yaml

PLATFORMS = ("youtube", "tiktok", "instagram")

DEFAULT_EMOTES = {
    "funny": ["LUL", "LULW", "OMEGALUL", "KEKW", "LMAO", "LOL", "ICANT", "pepeLaugh", "KEKL", "xdd"],
    "hype": ["Pog", "PogChamp", "PogU", "POGGERS", "W", "HOLY", "LETSGO", "EZ", "GIGACHAD", "clip"],
    "shock": ["???", "WHAT", "monkaS", "monkaW", "D:", "NOWAY", "Aware", "WTF"],
}

# Videos whose transcript contains any of these whole words are saved but never posted.
DEFAULT_BLOCKLIST: list[str] = [
    "nigger", "niggers", "nigga", "niggas", "faggot", "faggots", "fag", "fags", "retard", "retarded",
    "tranny", "trannies", "chink", "chinks", "spic", "spics", "kike", "kikes", "wetback", "gook",
    "kys",
]


@dataclass(frozen=True)
class Settings:
    top_n: int = 25
    game_name: str = "Grand Theft Auto VI"
    render_interval_min: int = 10
    discovery_interval_min: int = 5
    hype_threshold: float = 3.0
    min_post_score: float = 3.5
    channel_cooldown_s: int = 120
    max_clips_per_hour: int = 40
    bucket_s: int = 5
    baseline_window_s: int = 300
    trigger_buckets: int = 2
    freshness_hours: int = 6
    keep_days: int = 7
    quiet_hours: str | None = None
    active_hours: str | None = "10:00-23:00"  # only post inside these local hours, like a person would
    min_gap_min: int = 45            # minimum time between two posts on the same platform
    stagger_min: int = 10            # minimum time between posts on different platforms
    retry_after_fail_min: int = 30   # wait this long after a failed upload before trying again
    timezone: str | None = None  # IANA name for quiet hours; None = system local
    youtube_privacy: str = "public"
    graph_api_version: str = "v21.0"
    budgets: dict[str, int] = field(default_factory=lambda: {"youtube": 6, "tiktok": 10, "instagram": 20})
    # Posts per day, picked at random each day from this range (always capped by `budgets`).
    daily_posts: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {"youtube": (2, 4), "tiktok": (3, 6), "instagram": (2, 5)})
    enabled: dict[str, bool] = field(default_factory=lambda: {p: False for p in PLATFORMS})
    facecams: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    emotes: dict[str, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_EMOTES.items()})
    blocklist: list[str] = field(default_factory=lambda: list(DEFAULT_BLOCKLIST))
    channel_blocklist: list[str] = field(default_factory=list)
    data_dir: Path = Path("data")
    output_dir: Path = Path("output")
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""

    @property
    def db_path(self) -> Path:
        return self.data_dir / "clipbot.db"

    @property
    def tokens_path(self) -> Path:
        return self.data_dir / "tokens.json"


_ENV_KEYS = {
    "TWITCH_CLIENT_ID": "twitch_client_id",
    "TWITCH_CLIENT_SECRET": "twitch_client_secret",
    "GOOGLE_CLIENT_ID": "google_client_id",
    "GOOGLE_CLIENT_SECRET": "google_client_secret",
    "TIKTOK_CLIENT_KEY": "tiktok_client_key",
    "TIKTOK_CLIENT_SECRET": "tiktok_client_secret",
    "META_APP_ID": "meta_app_id",
    "META_APP_SECRET": "meta_app_secret",
}


def load_settings(config_path: Path | None, env: Mapping[str, str]) -> Settings:
    base = Settings()
    raw: dict[str, Any] = {}
    if config_path is not None and Path(config_path).exists():
        raw = yaml.safe_load(Path(config_path).read_text()) or {}
    known = {f.name for f in fields(Settings)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"Unknown setting(s) in {config_path}: {', '.join(sorted(unknown))}")

    kw: dict[str, Any] = {}
    for k, v in raw.items():
        if k in ("budgets", "enabled"):
            merged = dict(getattr(base, k))
            merged.update(v or {})
            kw[k] = merged
        elif k == "daily_posts":
            merged = dict(base.daily_posts)
            merged.update({p: (int(r[0]), int(r[1])) for p, r in (v or {}).items()})
            kw[k] = merged
        elif k == "emotes":
            merged = {c: list(e) for c, e in base.emotes.items()}
            merged.update({c: list(e) for c, e in (v or {}).items()})
            kw[k] = merged
        elif k == "facecams":
            kw[k] = {str(name).lower(): tuple(int(x) for x in box) for name, box in (v or {}).items()}
        elif k == "channel_blocklist":
            kw[k] = [str(c).lower() for c in (v or [])]
        elif k in ("data_dir", "output_dir"):
            kw[k] = Path(v)
        else:
            kw[k] = v
    for env_key, attr in _ENV_KEYS.items():
        if env.get(env_key):
            kw[attr] = env[env_key]
    return Settings(**{**{f.name: getattr(base, f.name) for f in fields(Settings)}, **kw})
