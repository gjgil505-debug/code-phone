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
