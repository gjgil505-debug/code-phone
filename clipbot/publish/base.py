"""Shared publisher interface."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class AuthError(Exception):
    """The platform login is missing, expired or revoked. Re-run `clipbot auth <platform>`."""


@dataclass(frozen=True)
class PostResult:
    remote_id: str
    url: str | None


class Publisher(Protocol):
    name: str

    async def publish(self, video_path: Path, meta: dict) -> PostResult: ...


def caption(meta: dict) -> str:
    """Full post caption: description (has the @streamer tag and credit) plus hashtags if missing."""
    text = meta.get("description") or meta.get("title", "")
    if f"@{meta.get('display_name', '')}" not in text and meta.get("display_name"):
        text = f"{text}\n@{meta['display_name']}"
    missing = [h for h in meta.get("hashtags", []) if h not in text]
    return (text + ("\n" + " ".join(missing) if missing else "")).strip()
