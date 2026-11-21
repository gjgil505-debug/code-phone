"""YouTube Shorts upload via the YouTube Data API v3."""
from __future__ import annotations

from pathlib import Path

import httpx

from clipbot.config import Settings
from clipbot.oauth import TokenStore
from clipbot.publish.base import AuthError, PostResult, caption

GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
SUFFIX = " #Shorts"


class YouTubePublisher:
    name = "youtube"

    def __init__(self, settings: Settings, tokens: TokenStore, client: httpx.AsyncClient):
        self.s, self.tokens, self.client = settings, tokens, client

    async def _refresh(self) -> str:
        tok = self.tokens.get("youtube") or {}
        r = await self.client.post(GOOGLE_TOKEN, data={
            "client_id": self.s.google_client_id, "client_secret": self.s.google_client_secret,
            "refresh_token": tok.get("refresh_token", ""), "grant_type": "refresh_token"})
        if r.status_code != 200:
            raise AuthError(f"YouTube login expired ({r.text[:200]}); run `clipbot auth youtube`")
        tok["access_token"] = r.json()["access_token"]
        self.tokens.put("youtube", tok)
        return tok["access_token"]

    async def publish(self, video_path: Path, meta: dict) -> PostResult:
        tok = self.tokens.get("youtube")
        if not tok:
            raise AuthError("no YouTube login; run `clipbot auth youtube`")
        data = Path(video_path).read_bytes()
        title = meta.get("title", "GTA 6")[: 100 - len(SUFFIX)] + SUFFIX
        body = {
            "snippet": {"title": title, "description": caption(meta)[:4900],
                        "tags": [h.lstrip("#") for h in meta.get("hashtags", [])], "categoryId": "20"},
            "status": {"privacyStatus": self.s.youtube_privacy, "selfDeclaredMadeForKids": False},
        }
        access = tok["access_token"]
        for attempt in range(2):
            r = await self.client.post(UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
                                       json=body, headers={"Authorization": f"Bearer {access}",
                                                           "X-Upload-Content-Type": "video/mp4",
                                                           "X-Upload-Content-Length": str(len(data))})
            if r.status_code == 401 and attempt == 0:
                access = await self._refresh()
                continue
            break
        if r.status_code == 401:
            raise AuthError("YouTube rejected the login; run `clipbot auth youtube`")
        if r.status_code != 200:
            raise RuntimeError(f"YouTube upload init failed {r.status_code}: {r.text[:300]}")
        up = await self.client.put(r.headers["Location"], content=data, timeout=600,
                                   headers={"Authorization": f"Bearer {access}", "Content-Type": "video/mp4"})
        if up.status_code not in (200, 201):
            raise RuntimeError(f"YouTube upload failed {up.status_code}: {up.text[:300]}")
        vid = up.json()["id"]
        return PostResult(vid, f"https://youtube.com/shorts/{vid}")
