"""Twitch Helix client: stream discovery and clip creation."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

from clipbot.config import Settings
from clipbot.oauth import TokenStore

log = logging.getLogger(__name__)
HELIX = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"


class TwitchAuthError(Exception):
    """The Twitch login is missing or can no longer be refreshed. Run `clipbot auth twitch`."""


@dataclass(frozen=True)
class StreamInfo:
    user_id: str
    login: str
    display_name: str
    viewers: int


@dataclass(frozen=True)
class ClipInfo:
    id: str
    url: str
    duration: float


class TwitchApi:
    def __init__(self, settings: Settings, tokens: TokenStore, client: httpx.AsyncClient,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.s = settings
        self.tokens = tokens
        self.client = client
        self.sleep = sleep
        self._app_token: str | None = None
        self._game_id: str | None = None

    # --- tokens ---
    async def _fetch_app_token(self) -> str:
        r = await self.client.post(TOKEN_URL, data={
            "client_id": self.s.twitch_client_id, "client_secret": self.s.twitch_client_secret,
            "grant_type": "client_credentials"})
        if r.status_code != 200:
            raise TwitchAuthError(f"could not get Twitch app token ({r.status_code}); check TWITCH_CLIENT_ID/SECRET")
        self._app_token = r.json()["access_token"]
        return self._app_token

    async def _refresh_user_token(self) -> str:
        tok = self.tokens.get("twitch") or {}
        r = await self.client.post(TOKEN_URL, data={
            "client_id": self.s.twitch_client_id, "client_secret": self.s.twitch_client_secret,
            "grant_type": "refresh_token", "refresh_token": tok.get("refresh_token", "")})
        if r.status_code != 200:
            raise TwitchAuthError("Twitch login expired; run `clipbot auth twitch`")
        new = r.json()
        tok.update(access_token=new["access_token"], refresh_token=new.get("refresh_token", tok.get("refresh_token")))
        self.tokens.put("twitch", tok)
        return tok["access_token"]

    async def _request(self, method: str, path: str, *, user: bool, params: dict) -> httpx.Response:
        if user:
            tok = self.tokens.get("twitch")
            if not tok:
                raise TwitchAuthError("no Twitch login; run `clipbot auth twitch`")
            bearer = tok["access_token"]
        else:
            bearer = self._app_token or await self._fetch_app_token()
        for attempt in range(2):
            r = await self.client.request(method, f"{HELIX}{path}", params=params, headers={
                "Client-Id": self.s.twitch_client_id, "Authorization": f"Bearer {bearer}"})
            if r.status_code != 401 or attempt == 1:
                return r
            bearer = await self._refresh_user_token() if user else await self._fetch_app_token()
        return r

    # --- discovery ---
    async def _game(self) -> str | None:
        if self._game_id is None:
            r = await self._request("GET", "/games", user=False, params={"name": self.s.game_name})
            r.raise_for_status()
            data = r.json()["data"]
            if not data:
                log.warning("Twitch has no category named %r", self.s.game_name)
                return None
            self._game_id = data[0]["id"]
        return self._game_id

    async def top_streams(self) -> list[StreamInfo]:
        game = await self._game()
        if game is None:
            return []
        r = await self._request("GET", "/streams", user=False,
                                params={"game_id": game, "first": 100, "type": "live"})
        r.raise_for_status()
        block = set(self.s.channel_blocklist)
        streams = [StreamInfo(d["user_id"], d["user_login"].lower(), d["user_name"], int(d["viewer_count"]))
                   for d in r.json()["data"] if d["user_login"].lower() not in block]
        streams.sort(key=lambda s: s.viewers, reverse=True)
        return streams[: self.s.top_n]

    # --- clips ---
    async def create_clip(self, broadcaster_id: str) -> str | None:
        r = await self._request("POST", "/clips", user=True, params={"broadcaster_id": broadcaster_id})
        if r.status_code in (403, 404):
            log.info("clipping unavailable for %s: %s", broadcaster_id, r.text[:200])
            return None
        if r.status_code == 401:
            raise TwitchAuthError("Twitch rejected the login; run `clipbot auth twitch`")
        r.raise_for_status()
        return r.json()["data"][0]["id"]

    async def wait_clip(self, clip_id: str, timeout_s: float = 20) -> ClipInfo | None:
        waited = 0.0
        while waited < timeout_s:
            await self.sleep(2)
            waited += 2
            r = await self._request("GET", "/clips", user=False, params={"id": clip_id})
            if r.status_code == 200 and r.json()["data"]:
                d = r.json()["data"][0]
                return ClipInfo(d["id"], d["url"], float(d.get("duration", 0)))
        return None
