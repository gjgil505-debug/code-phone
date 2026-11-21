"""Instagram Reels via the Instagram Graph API (resumable upload)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable

import httpx

from clipbot.config import Settings
from clipbot.oauth import TokenStore
from clipbot.publish.base import AuthError, PostResult, caption

GRAPH = "https://graph.facebook.com"
STATUS_TIMEOUT_S = 300


class InstagramPublisher:
    name = "instagram"

    def __init__(self, settings: Settings, tokens: TokenStore, client: httpx.AsyncClient,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.s, self.tokens, self.client, self.sleep = settings, tokens, client, sleep

    def _check(self, r: httpx.Response, what: str) -> dict:
        try:
            body = r.json()
        except ValueError:
            body = {}
        err = body.get("error") if isinstance(body, dict) else None
        # Only token problems mean "log in again"; Meta labels almost every error OAuthException.
        if err and (err.get("code") in (102, 190) or err.get("error_subcode") in (458, 459, 460, 463, 464, 467)):
            raise AuthError(f"Instagram login invalid ({err.get('message')}); run `clipbot auth instagram`")
        if r.status_code != 200:
            raise RuntimeError(f"Instagram {what} failed {r.status_code}: {r.text[:300]}")
        return body

    async def publish(self, video_path: Path, meta: dict) -> PostResult:
        tok = self.tokens.get("instagram")
        if not tok:
            raise AuthError("no Instagram login; run `clipbot auth instagram`")
        token, ig = tok["page_token"], tok["ig_user_id"]
        base = f"{GRAPH}/{self.s.graph_api_version}"
        data = Path(video_path).read_bytes()
        c = self._check(await self.client.post(f"{base}/{ig}/media", data={
            "media_type": "REELS", "upload_type": "resumable", "caption": caption(meta)[:2200],
            "share_to_feed": "true", "access_token": token}), "container")
        self._check(await self.client.post(c["uri"], content=data, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data))}), "upload")
        waited = 0
        while True:
            st = self._check(await self.client.get(f"{base}/{c['id']}", params={
                "fields": "status_code,status", "access_token": token}), "status")
            code = st.get("status_code")
            if code == "FINISHED":
                break
            if code in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Instagram processing {code}: {st.get('status')}")
            if waited >= STATUS_TIMEOUT_S:
                raise RuntimeError("Instagram processing timed out")
            await self.sleep(5)
            waited += 5
        p = self._check(await self.client.post(f"{base}/{ig}/media_publish", data={
            "creation_id": c["id"], "access_token": token}), "publish")
        return PostResult(p["id"], None)
