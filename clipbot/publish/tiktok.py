"""TikTok Content Posting API (Direct Post, file upload)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable

import httpx

from clipbot.config import Settings
from clipbot.oauth import TokenStore
from clipbot.publish.base import AuthError, PostResult

TT = "https://open.tiktokapis.com"
CHUNK = 10 * 1024 * 1024
MIN_CHUNK = 5 * 1024 * 1024
STATUS_TIMEOUT_S = 300


def chunk_plan(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count). Files under 5 MB go in one piece; the last chunk takes the remainder."""
    if size < MIN_CHUNK or size <= CHUNK:
        return size, 1
    return CHUNK, size // CHUNK


class TikTokPublisher:
    name = "tiktok"

    def __init__(self, settings: Settings, tokens: TokenStore, client: httpx.AsyncClient,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.s, self.tokens, self.client, self.sleep = settings, tokens, client, sleep

    async def _refresh(self) -> None:
        tok = self.tokens.get("tiktok") or {}
        r = await self.client.post(f"{TT}/v2/oauth/token/", data={
            "client_key": self.s.tiktok_client_key, "client_secret": self.s.tiktok_client_secret,
            "grant_type": "refresh_token", "refresh_token": tok.get("refresh_token", "")})
        if r.status_code != 200 or "access_token" not in r.json():
            raise AuthError(f"TikTok login expired ({r.text[:200]}); run `clipbot auth tiktok`")
        new = r.json()
        tok.update(access_token=new["access_token"], refresh_token=new.get("refresh_token", tok.get("refresh_token")))
        self.tokens.put("tiktok", tok)

    async def _call(self, path: str, body: dict) -> dict:
        for attempt in range(2):
            tok = self.tokens.get("tiktok")
            if not tok:
                raise AuthError("no TikTok login; run `clipbot auth tiktok`")
            r = await self.client.post(f"{TT}{path}", json=body, headers={
                "Authorization": f"Bearer {tok['access_token']}", "Content-Type": "application/json; charset=UTF-8"})
            if r.status_code == 401 and attempt == 0:
                await self._refresh()
                continue
            break
        if r.status_code == 401:
            raise AuthError("TikTok rejected the login; run `clipbot auth tiktok`")
        err = (r.json().get("error") or {}) if r.headers.get("content-type", "").startswith("application/json") \
            else {}
        if r.status_code != 200 or err.get("code") not in (None, "ok"):
            raise RuntimeError(f"TikTok {path} failed {r.status_code}: {r.text[:300]}")
        return r.json()["data"]

    async def publish(self, video_path: Path, meta: dict) -> PostResult:
        data = Path(video_path).read_bytes()
        info = await self._call("/v2/post/publish/creator_info/query/", {})
        options = info.get("privacy_level_options", [])
        privacy = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in options else "SELF_ONLY"
        title = f"{meta.get('title', '')} @{meta.get('display_name', '')} {' '.join(meta.get('hashtags', []))}"
        size = len(data)
        chunk, count = chunk_plan(size)
        init = await self._call("/v2/post/publish/video/init/", {
            "post_info": {"title": title.strip()[:2200], "privacy_level": privacy, "disable_duet": False,
                          "disable_comment": False, "disable_stitch": False, "video_cover_timestamp_ms": 1000},
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
                            "total_chunk_count": count},
        })
        for i in range(count):
            start = i * chunk
            end = size if i == count - 1 else start + chunk
            r = await self.client.put(init["upload_url"], content=data[start:end], timeout=600, headers={
                "Content-Type": "video/mp4", "Content-Range": f"bytes {start}-{end - 1}/{size}"})
            if r.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok chunk upload failed {r.status_code}: {r.text[:300]}")
        waited = 0
        while waited <= STATUS_TIMEOUT_S:
            st = await self._call("/v2/post/publish/status/fetch/", {"publish_id": init["publish_id"]})
            if st.get("status") == "PUBLISH_COMPLETE":
                return PostResult(init["publish_id"], None)
            if st.get("status") == "FAILED":
                raise RuntimeError(f"TikTok publish failed: {st.get('fail_reason')}")
            await self.sleep(5)
            waited += 5
        raise RuntimeError("TikTok publish timed out")
