"""`clipbot setup`: enter keys one at a time instead of editing files on a phone screen."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import yaml

TWITCH = [("TWITCH_CLIENT_ID", "Twitch Client ID"), ("TWITCH_CLIENT_SECRET", "Twitch Client Secret")]
PLATFORM_KEYS = {
    "youtube": ("YouTube Shorts", [("GOOGLE_CLIENT_ID", "Google OAuth Client ID"),
                                   ("GOOGLE_CLIENT_SECRET", "Google OAuth Client Secret")]),
    "tiktok": ("TikTok", [("TIKTOK_CLIENT_KEY", "TikTok Client Key"),
                          ("TIKTOK_CLIENT_SECRET", "TikTok Client Secret")]),
    "instagram": ("Instagram Reels", [("META_APP_ID", "Meta App ID"), ("META_APP_SECRET", "Meta App Secret")]),
}


def read_env(path: Path) -> dict[str, str]:
    out = {}
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def write_env(path: Path, values: dict[str, str]) -> None:
    path = Path(path)
    lines = path.read_text().splitlines() if path.exists() else []
    todo = dict(values)
    for i, line in enumerate(lines):
        k = line.partition("=")[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and k in todo:
            lines[i] = f"{k}={todo.pop(k)}"
    lines += [f"{k}={v}" for k, v in todo.items()]
    path.write_text("\n".join(lines) + "\n")
    os.chmod(path, 0o600)


def enable_platforms(config_path: Path, enabled: dict[str, bool]) -> None:
    config_path = Path(config_path)
    data = (yaml.safe_load(config_path.read_text()) if config_path.exists() else None) or {}
    data["enabled"] = dict(enabled)
    config_path.write_text(yaml.safe_dump(data, sort_keys=False))


def run_wizard(env_path: Path, config_path: Path, ask: Callable[[str], str] = input,
               say: Callable[[str], None] = print) -> None:
    current = read_env(env_path)
    new: dict[str, str] = {}

    def key(name: str, label: str) -> None:
        have = " (press Enter to keep the saved one)" if current.get(name) else ""
        val = ask(f"{label}{have}: ").strip()
        if val:
            new[name] = val

    say("Paste each key when asked. Long-press in the terminal to paste.\n")
    for name, label in TWITCH:
        key(name, label)
    enabled = {}
    for platform, (title, keys) in PLATFORM_KEYS.items():
        enabled[platform] = ask(f"Post to {title}? (y/n): ").strip().lower().startswith("y")
        if enabled[platform]:
            for name, label in keys:
                key(name, label)
    if new:
        write_env(env_path, new)
    enable_platforms(config_path, enabled)
    say("\nSaved. Now log in to each account (copy each command, one at a time):")
    say("  clipbot auth twitch")
    for platform, on in enabled.items():
        if on:
            say(f"  clipbot auth {platform}")
    say("Then start the bot:  sudo systemctl restart clipbot")
    say("Check on it any time:  clipbot status")
