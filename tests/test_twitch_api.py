import json

import httpx
import pytest
import respx

from clipbot.config import Settings
from clipbot.oauth import TokenStore
from clipbot.twitch.api import HELIX, TOKEN_URL, TwitchApi, TwitchAuthError

S = Settings(twitch_client_id="cid", twitch_client_secret="sec")


async def _nosleep(_):
    return None


def _api(tmp_path, settings=S, user_token=True):
    tokens = TokenStore(tmp_path / "tokens.json")
    if user_token:
        tokens.put("twitch", {"access_token": "u1", "refresh_token": "r1"})
    return TwitchApi(settings, tokens, httpx.AsyncClient(), sleep=_nosleep), tokens


def _mock_app_token(router):
    return router.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "app", "expires_in": 3600}))


def _streams(n):
    return [{"user_id": str(i), "user_login": f"s{i}", "user_name": f"S{i}", "viewer_count": v}
            for i, v in enumerate(range(n))]


@respx.mock
async def test_top_streams_sorted_and_limited(tmp_path):
    _mock_app_token(respx)
    games = respx.get(f"{HELIX}/games").mock(return_value=httpx.Response(200, json={"data": [{"id": "999"}]}))
    streams = respx.get(f"{HELIX}/streams").mock(return_value=httpx.Response(200, json={"data": _streams(30)}))
    api, _ = _api(tmp_path)
    out = await api.top_streams()
    assert len(out) == 25
    assert [s.viewers for s in out] == sorted([s.viewers for s in out], reverse=True)
    assert out[0].login == "s29" and out[0].display_name == "S29" and out[0].user_id == "29"
    assert games.calls[0].request.url.params["name"] == "Grand Theft Auto VI"
    assert streams.calls[0].request.url.params["game_id"] == "999"
    assert streams.calls[0].request.headers["Client-Id"] == "cid"
    assert streams.calls[0].request.headers["Authorization"] == "Bearer app"
    await api.top_streams()
    assert games.call_count == 1  # game id cached


@respx.mock
async def test_top_streams_excludes_blocklist(tmp_path):
    _mock_app_token(respx)
    respx.get(f"{HELIX}/games").mock(return_value=httpx.Response(200, json={"data": [{"id": "9"}]}))
    respx.get(f"{HELIX}/streams").mock(return_value=httpx.Response(200, json={"data": _streams(5)}))
    api, _ = _api(tmp_path, Settings(twitch_client_id="cid", twitch_client_secret="sec", channel_blocklist=["s4"]))
    assert "s4" not in [s.login for s in await api.top_streams()]


@respx.mock
async def test_unknown_game_returns_empty(tmp_path):
    _mock_app_token(respx)
    respx.get(f"{HELIX}/games").mock(return_value=httpx.Response(200, json={"data": []}))
    api, _ = _api(tmp_path)
    assert await api.top_streams() == []


@respx.mock
async def test_create_clip_returns_id(tmp_path):
    route = respx.post(f"{HELIX}/clips").mock(return_value=httpx.Response(202, json={"data": [{"id": "Clip1"}]}))
    api, _ = _api(tmp_path)
    assert await api.create_clip("123") == "Clip1"
    req = route.calls[0].request
    assert req.url.params["broadcaster_id"] == "123"
    assert req.headers["Authorization"] == "Bearer u1"


@respx.mock
@pytest.mark.parametrize("status", [403, 404])
async def test_create_clip_disabled_returns_none(tmp_path, status):
    respx.post(f"{HELIX}/clips").mock(return_value=httpx.Response(status, json={"message": "nope"}))
    api, _ = _api(tmp_path)
    assert await api.create_clip("123") is None


@respx.mock
async def test_user_token_refreshed_on_401(tmp_path):
    respx.post(f"{HELIX}/clips").mock(side_effect=[
        httpx.Response(401, json={"message": "Invalid OAuth token"}),
        httpx.Response(202, json={"data": [{"id": "Clip2"}]}),
    ])
    refresh = respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": "u2", "refresh_token": "r2"}))
    api, tokens = _api(tmp_path)
    assert await api.create_clip("1") == "Clip2"
    body = dict(x.split("=") for x in refresh.calls[0].request.content.decode().split("&"))
    assert body["grant_type"] == "refresh_token" and body["refresh_token"] == "r1"
    assert tokens.get("twitch")["access_token"] == "u2"
    assert TokenStore(tmp_path / "tokens.json").get("twitch")["refresh_token"] == "r2"


@respx.mock
async def test_refresh_failure_raises_auth_error(tmp_path):
    respx.post(f"{HELIX}/clips").mock(return_value=httpx.Response(401))
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"message": "Invalid refresh token"}))
    api, _ = _api(tmp_path)
    with pytest.raises(TwitchAuthError):
        await api.create_clip("1")


async def test_create_clip_without_user_token_raises(tmp_path):
    api, _ = _api(tmp_path, user_token=False)
    with pytest.raises(TwitchAuthError):
        await api.create_clip("1")


@respx.mock
async def test_wait_clip_returns_info(tmp_path):
    respx.get(f"{HELIX}/clips").mock(side_effect=[
        httpx.Response(200, json={"data": []}),
        httpx.Response(200, json={"data": [{"id": "C", "url": "https://clips.twitch.tv/C", "duration": 30.0}]}),
    ])
    _mock_app_token(respx)
    api, _ = _api(tmp_path)
    info = await api.wait_clip("C")
    assert (info.id, info.url, info.duration) == ("C", "https://clips.twitch.tv/C", 30.0)


@respx.mock
async def test_wait_clip_times_out_returns_none(tmp_path):
    respx.get(f"{HELIX}/clips").mock(return_value=httpx.Response(200, json={"data": []}))
    _mock_app_token(respx)
    api, _ = _api(tmp_path)
    assert await api.wait_clip("C", timeout_s=6) is None


def test_token_store_atomic_roundtrip(tmp_path):
    t = TokenStore(tmp_path / "d" / "tokens.json")
    assert t.get("x") is None
    t.put("x", {"a": 1})
    t.put("y", {"b": 2})
    assert json.loads((tmp_path / "d" / "tokens.json").read_text()) == {"x": {"a": 1}, "y": {"b": 2}}
