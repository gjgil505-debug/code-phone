"""Token storage and OAuth login helpers."""
from __future__ import annotations

import asyncio
import http.server
import json
import os
import secrets
import tempfile
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from clipbot.config import Settings


class TokenStore:
    """JSON file of tokens keyed by provider name, written atomically."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}

    def get(self, name: str) -> dict | None:
        with self._lock:
            return self._read().get(name)

    def put(self, name: str, token: dict) -> None:
        with self._lock:
            data = self._read()
            data[name] = token
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".tokens-")
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)


# ---------------- OAuth login (one-time, interactive) ----------------
DEFAULT_REDIRECT = "http://localhost:8765/callback"
SCOPES = {
    "twitch": "clips:edit",
    "youtube": "https://www.googleapis.com/auth/youtube.upload",
    "tiktok": "user.info.basic,video.publish",
    "instagram": "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement,business_management",
}


class AuthSetupError(Exception):
    pass


def authorize_url(provider: str, s: Settings, state: str, redirect_uri: str) -> str:
    scope = SCOPES[provider]
    if provider == "twitch":
        return "https://id.twitch.tv/oauth2/authorize?" + urlencode({
            "client_id": s.twitch_client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": scope, "state": state, "force_verify": "true"})
    if provider == "youtube":
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": s.google_client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": scope, "state": state, "access_type": "offline", "prompt": "consent"})
    if provider == "tiktok":
        return "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
            "client_key": s.tiktok_client_key, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": scope, "state": state})
    if provider == "instagram":
        return f"https://www.facebook.com/{s.graph_api_version}/dialog/oauth?" + urlencode({
            "client_id": s.meta_app_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": scope, "state": state})
    raise AuthSetupError(f"unknown provider {provider}")


def parse_redirect(url: str, state: str) -> str:
    q = parse_qs(urlparse(url.strip()).query)
    if q.get("error"):
        raise AuthSetupError(f"login was refused: {q['error'][0]} {q.get('error_description', [''])[0]}")
    if q.get("state", [None])[0] != state:
        raise AuthSetupError("login response did not match this request (state mismatch); try again")
    if not q.get("code"):
        raise AuthSetupError("no authorization code in the redirect URL")
    return q["code"][0]


def _ok(r: httpx.Response, what: str) -> dict:
    if r.status_code != 200:
        raise AuthSetupError(f"{what} failed ({r.status_code}): {r.text[:300]}")
    return r.json()


async def exchange_code(provider: str, s: Settings, code: str, redirect_uri: str,
                        client: httpx.AsyncClient) -> dict:
    if provider == "twitch":
        d = _ok(await client.post("https://id.twitch.tv/oauth2/token", data={
            "client_id": s.twitch_client_id, "client_secret": s.twitch_client_secret, "code": code,
            "grant_type": "authorization_code", "redirect_uri": redirect_uri}), "Twitch login")
        return {"access_token": d["access_token"], "refresh_token": d["refresh_token"]}
    if provider == "youtube":
        d = _ok(await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": s.google_client_id, "client_secret": s.google_client_secret, "code": code,
            "grant_type": "authorization_code", "redirect_uri": redirect_uri}), "Google login")
        if "refresh_token" not in d:
            raise AuthSetupError("Google did not return a refresh token; remove the app's access at "
                                 "myaccount.google.com/permissions and run this again")
        return {"access_token": d["access_token"], "refresh_token": d["refresh_token"]}
    if provider == "tiktok":
        d = _ok(await client.post("https://open.tiktokapis.com/v2/oauth/token/", data={
            "client_key": s.tiktok_client_key, "client_secret": s.tiktok_client_secret, "code": code,
            "grant_type": "authorization_code", "redirect_uri": redirect_uri}), "TikTok login")
        if "access_token" not in d:
            raise AuthSetupError(f"TikTok login failed: {d}")
        return {"access_token": d["access_token"], "refresh_token": d["refresh_token"], "open_id": d.get("open_id")}
    if provider == "instagram":
        base = f"https://graph.facebook.com/{s.graph_api_version}"
        short = _ok(await client.get(f"{base}/oauth/access_token", params={
            "client_id": s.meta_app_id, "client_secret": s.meta_app_secret, "redirect_uri": redirect_uri,
            "code": code}), "Facebook login")["access_token"]
        long = _ok(await client.get(f"{base}/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": s.meta_app_id, "client_secret": s.meta_app_secret,
            "fb_exchange_token": short}), "Facebook long-lived token")["access_token"]
        # Page tokens obtained from a long-lived user token do not expire.
        pages = _ok(await client.get(f"{base}/me/accounts", params={
            "fields": "name,access_token,instagram_business_account", "access_token": long}),
            "listing Facebook Pages")["data"]
        for p in pages:
            if p.get("instagram_business_account"):
                return {"page_token": p["access_token"], "ig_user_id": p["instagram_business_account"]["id"],
                        "page_name": p["name"]}
        raise AuthSetupError("none of your Facebook Pages has an Instagram Professional account linked; "
                             "link one in Instagram settings and run this again")
    raise AuthSetupError(f"unknown provider {provider}")


def _wait_for_local_redirect(redirect_uri: str, timeout_s: float = 300) -> str:
    u = urlparse(redirect_uri)
    got: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if urlparse(self.path).path != u.path:
                self.send_response(404)
                self.end_headers()
                return
            got["url"] = f"{redirect_uri.split('?')[0]}?{urlparse(self.path).query}"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>clipbot: login received. You can close this tab.</h2>")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer((u.hostname, u.port or 80), Handler)
    server.timeout = 1
    t = threading.Thread(target=lambda: [server.handle_request() for _ in range(int(timeout_s))
                                          if "url" not in got], daemon=True)
    t.start()
    t.join(timeout_s)
    server.server_close()
    if "url" not in got:
        raise AuthSetupError("timed out waiting for the login redirect")
    return got["url"]


def use_paste_mode(redirect_uri: str, env) -> bool:
    """Ask the user to paste the redirected address instead of listening for it locally.

    Needed when the browser is on another device (a phone talking to a server over SSH), or when the
    redirect page isn't this machine.
    """
    if urlparse(redirect_uri).hostname not in ("localhost", "127.0.0.1"):
        return True
    return bool(env.get("SSH_CONNECTION") or env.get("SSH_TTY") or env.get("CLIPBOT_PASTE_LOGIN"))


async def run_oauth(provider: str, s: Settings, tokens: TokenStore, redirect_uri: str = DEFAULT_REDIRECT,
                    paste: bool | None = None) -> dict:
    state = secrets.token_urlsafe(16)
    url = authorize_url(provider, s, state, redirect_uri)
    if paste is None:
        paste = use_paste_mode(redirect_uri, os.environ)
    print(f"\nOpen this link, log in and approve:\n\n{url}\n")
    if paste:
        print("After you approve, your browser goes to a page that may not load (that's expected).\n"
              "Copy the full address from the address bar and paste it here.")
        redirected = input("Paste the address: ")
    else:
        try:
            webbrowser.open(url)
        except Exception:
            pass
        print(f"Waiting for the redirect to {redirect_uri} ...")
        redirected = await asyncio.to_thread(_wait_for_local_redirect, redirect_uri)
    code = parse_redirect(redirected, state)
    async with httpx.AsyncClient(timeout=60) as client:
        tok = await exchange_code(provider, s, code, redirect_uri, client)
    tokens.put(provider, tok)
    return tok
