import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from clipbot.config import Settings
from clipbot.oauth import TokenStore, authorize_url
from clipbot.publish.base import AuthError
from clipbot.publish.instagram import GRAPH, InstagramPublisher
from clipbot.publish.tiktok import TT, TikTokPublisher
from clipbot.publish.youtube import GOOGLE_TOKEN, UPLOAD_URL, YouTubePublisher

S = Settings(google_client_id="g", google_client_secret="gs", tiktok_client_key="tk", tiktok_client_secret="ts",
             meta_app_id="m", meta_app_secret="ms", twitch_client_id="tw", twitch_client_secret="tws")
META = {"title": "Nobody Expected This", "description": "Nobody Expected This\n\nStreamer: @StreamerName",
        "hashtags": ["#GTA6", "#shorts"], "display_name": "StreamerName"}


async def _nosleep(_):
    pass


def _video(tmp_path, size=1000):
    p = tmp_path / "v.mp4"
    with open(p, "wb") as f:
        f.truncate(size)
    return p


def _tokens(tmp_path, name, tok):
    t = TokenStore(tmp_path / "tokens.json")
    t.put(name, tok)
    return t


# ---------- YouTube ----------
@respx.mock
async def test_youtube_upload_happy_path(tmp_path):
    init = respx.post(UPLOAD_URL).mock(return_value=httpx.Response(200, headers={"Location": "https://up/1"}))
    put = respx.put("https://up/1").mock(return_value=httpx.Response(200, json={"id": "abc"}))
    pub = YouTubePublisher(S, _tokens(tmp_path, "youtube", {"access_token": "a", "refresh_token": "r"}),
                           httpx.AsyncClient())
    res = await pub.publish(_video(tmp_path), META)
    assert res.url == "https://youtube.com/shorts/abc" and res.remote_id == "abc"
    body = json.loads(init.calls[0].request.content)
    assert body["snippet"]["title"].endswith(" #Shorts") and len(body["snippet"]["title"]) <= 100
    assert "@StreamerName" in body["snippet"]["description"]
    assert body["status"]["privacyStatus"] == "public"
    assert init.calls[0].request.headers["Authorization"] == "Bearer a"
    assert len(put.calls[0].request.content) == 1000


@respx.mock
async def test_youtube_refreshes_then_uploads(tmp_path):
    respx.post(UPLOAD_URL).mock(side_effect=[httpx.Response(401),
                                             httpx.Response(200, headers={"Location": "https://up/1"})])
    respx.put("https://up/1").mock(return_value=httpx.Response(201, json={"id": "abc"}))
    respx.post(GOOGLE_TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "a2"}))
    tokens = _tokens(tmp_path, "youtube", {"access_token": "a", "refresh_token": "r"})
    await YouTubePublisher(S, tokens, httpx.AsyncClient()).publish(_video(tmp_path), META)
    assert tokens.get("youtube") == {"access_token": "a2", "refresh_token": "r"}


@respx.mock
async def test_youtube_invalid_grant_raises_auth_error(tmp_path):
    respx.post(UPLOAD_URL).mock(return_value=httpx.Response(401))
    respx.post(GOOGLE_TOKEN).mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    pub = YouTubePublisher(S, _tokens(tmp_path, "youtube", {"access_token": "a", "refresh_token": "r"}),
                           httpx.AsyncClient())
    with pytest.raises(AuthError):
        await pub.publish(_video(tmp_path), META)


async def test_youtube_without_login_raises_auth_error(tmp_path):
    with pytest.raises(AuthError):
        await YouTubePublisher(S, TokenStore(tmp_path / "t.json"), httpx.AsyncClient()).publish(_video(tmp_path), META)


@respx.mock
async def test_youtube_quota_exceeded_is_not_auth_error(tmp_path):
    respx.post(UPLOAD_URL).mock(return_value=httpx.Response(
        403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}}))
    pub = YouTubePublisher(S, _tokens(tmp_path, "youtube", {"access_token": "a", "refresh_token": "r"}),
                           httpx.AsyncClient())
    with pytest.raises(RuntimeError, match="quotaExceeded"):
        await pub.publish(_video(tmp_path), META)


# ---------- TikTok ----------
def _tt_routes(privacy_options, statuses):
    respx.post(f"{TT}/v2/post/publish/creator_info/query/").mock(return_value=httpx.Response(
        200, json={"data": {"privacy_level_options": privacy_options}, "error": {"code": "ok"}}))
    init = respx.post(f"{TT}/v2/post/publish/video/init/").mock(return_value=httpx.Response(
        200, json={"data": {"publish_id": "pid", "upload_url": "https://tt-up/1"}, "error": {"code": "ok"}}))
    put = respx.put("https://tt-up/1").mock(return_value=httpx.Response(201))
    respx.post(f"{TT}/v2/post/publish/status/fetch/").mock(side_effect=[
        httpx.Response(200, json={"data": {"status": s, "fail_reason": "boom"}, "error": {"code": "ok"}})
        for s in statuses])
    return init, put


@respx.mock
async def test_tiktok_uses_self_only_when_public_not_offered(tmp_path):
    init, _ = _tt_routes(["SELF_ONLY"], ["PROCESSING_UPLOAD", "PUBLISH_COMPLETE"])
    pub = TikTokPublisher(S, _tokens(tmp_path, "tiktok", {"access_token": "a", "refresh_token": "r"}),
                          httpx.AsyncClient(), sleep=_nosleep)
    res = await pub.publish(_video(tmp_path), META)
    body = json.loads(init.calls[0].request.content)
    assert body["post_info"]["privacy_level"] == "SELF_ONLY"
    assert "@StreamerName" in body["post_info"]["title"]
    assert res.remote_id == "pid"


@respx.mock
async def test_tiktok_public_when_offered(tmp_path):
    init, _ = _tt_routes(["PUBLIC_TO_EVERYONE", "SELF_ONLY"], ["PUBLISH_COMPLETE"])
    pub = TikTokPublisher(S, _tokens(tmp_path, "tiktok", {"access_token": "a", "refresh_token": "r"}),
                          httpx.AsyncClient(), sleep=_nosleep)
    await pub.publish(_video(tmp_path), META)
    assert json.loads(init.calls[0].request.content)["post_info"]["privacy_level"] == "PUBLIC_TO_EVERYONE"


@respx.mock
async def test_tiktok_chunks_large_file(tmp_path):
    init, put = _tt_routes(["SELF_ONLY"], ["PUBLISH_COMPLETE"])
    size = 25 * 1024 * 1024
    pub = TikTokPublisher(S, _tokens(tmp_path, "tiktok", {"access_token": "a", "refresh_token": "r"}),
                          httpx.AsyncClient(), sleep=_nosleep)
    await pub.publish(_video(tmp_path, size), META)
    src = json.loads(init.calls[0].request.content)["source_info"]
    assert src == {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": 10 * 1024 * 1024,
                   "total_chunk_count": 2}
    ranges = [c.request.headers["Content-Range"] for c in put.calls]
    assert ranges == [f"bytes 0-{10 * 1024 * 1024 - 1}/{size}", f"bytes {10 * 1024 * 1024}-{size - 1}/{size}"]


@respx.mock
async def test_tiktok_small_file_single_chunk(tmp_path):
    init, put = _tt_routes(["SELF_ONLY"], ["PUBLISH_COMPLETE"])
    pub = TikTokPublisher(S, _tokens(tmp_path, "tiktok", {"access_token": "a", "refresh_token": "r"}),
                          httpx.AsyncClient(), sleep=_nosleep)
    await pub.publish(_video(tmp_path, 3000), META)
    assert json.loads(init.calls[0].request.content)["source_info"]["total_chunk_count"] == 1
    assert put.calls[0].request.headers["Content-Range"] == "bytes 0-2999/3000"


@respx.mock
async def test_tiktok_failed_status_raises(tmp_path):
    _tt_routes(["SELF_ONLY"], ["FAILED"])
    pub = TikTokPublisher(S, _tokens(tmp_path, "tiktok", {"access_token": "a", "refresh_token": "r"}),
                          httpx.AsyncClient(), sleep=_nosleep)
    with pytest.raises(RuntimeError, match="boom"):
        await pub.publish(_video(tmp_path), META)


@respx.mock
async def test_tiktok_expired_refresh_raises_auth_error(tmp_path):
    respx.post(f"{TT}/v2/post/publish/creator_info/query/").mock(return_value=httpx.Response(
        401, json={"error": {"code": "access_token_invalid"}}))
    respx.post(f"{TT}/v2/oauth/token/").mock(return_value=httpx.Response(
        400, json={"error": "invalid_grant"}))
    pub = TikTokPublisher(S, _tokens(tmp_path, "tiktok", {"access_token": "a", "refresh_token": "r"}),
                          httpx.AsyncClient(), sleep=_nosleep)
    with pytest.raises(AuthError):
        await pub.publish(_video(tmp_path), META)


# ---------- Instagram ----------
def _ig_routes(statuses):
    v = Settings().graph_api_version
    create = respx.post(f"{GRAPH}/{v}/IG1/media").mock(return_value=httpx.Response(
        200, json={"id": "CON1", "uri": "https://rupload.facebook.com/ig-api-upload/CON1"}))
    up = respx.post("https://rupload.facebook.com/ig-api-upload/CON1").mock(
        return_value=httpx.Response(200, json={"success": True}))
    respx.get(f"{GRAPH}/{v}/CON1").mock(side_effect=[
        httpx.Response(200, json={"status_code": s, "status": "err detail"}) for s in statuses])
    pubr = respx.post(f"{GRAPH}/{v}/IG1/media_publish").mock(return_value=httpx.Response(200, json={"id": "M1"}))
    return create, up, pubr


@respx.mock
async def test_instagram_container_poll_then_publish(tmp_path):
    create, up, pubr = _ig_routes(["IN_PROGRESS", "FINISHED"])
    pub = InstagramPublisher(S, _tokens(tmp_path, "instagram", {"page_token": "pt", "ig_user_id": "IG1"}),
                             httpx.AsyncClient(), sleep=_nosleep)
    res = await pub.publish(_video(tmp_path, 1234), META)
    assert res.remote_id == "M1"
    params = parse_qs(create.calls[0].request.content.decode())
    assert params["media_type"] == ["REELS"] and params["upload_type"] == ["resumable"]
    assert "@StreamerName" in params["caption"][0]
    h = up.calls[0].request.headers
    assert h["Authorization"] == "OAuth pt" and h["offset"] == "0" and h["file_size"] == "1234"
    assert parse_qs(pubr.calls[0].request.content.decode())["creation_id"] == ["CON1"]


@respx.mock
async def test_instagram_error_status_raises(tmp_path):
    _ig_routes(["ERROR"])
    pub = InstagramPublisher(S, _tokens(tmp_path, "instagram", {"page_token": "pt", "ig_user_id": "IG1"}),
                             httpx.AsyncClient(), sleep=_nosleep)
    with pytest.raises(RuntimeError, match="ERROR"):
        await pub.publish(_video(tmp_path), META)


@respx.mock
async def test_instagram_expired_token_raises_auth_error(tmp_path):
    v = Settings().graph_api_version
    respx.post(f"{GRAPH}/{v}/IG1/media").mock(return_value=httpx.Response(
        400, json={"error": {"code": 190, "message": "Error validating access token"}}))
    pub = InstagramPublisher(S, _tokens(tmp_path, "instagram", {"page_token": "pt", "ig_user_id": "IG1"}),
                             httpx.AsyncClient(), sleep=_nosleep)
    with pytest.raises(AuthError):
        await pub.publish(_video(tmp_path), META)


# ---------- OAuth URLs ----------
@pytest.mark.parametrize("provider,host,scope_key,scope", [
    ("twitch", "id.twitch.tv", "scope", "clips:edit"),
    ("youtube", "accounts.google.com", "scope", "https://www.googleapis.com/auth/youtube.upload"),
    ("tiktok", "www.tiktok.com", "scope", "user.info.basic,video.publish"),
    ("instagram", "www.facebook.com", "scope",
     "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement,business_management"),
])
def test_oauth_builds_authorize_url_with_scopes(provider, host, scope_key, scope):
    url = urlparse(authorize_url(provider, S, "st8", "http://localhost:8765/callback"))
    q = parse_qs(url.query)
    assert url.hostname == host
    assert q[scope_key] == [scope] and q["state"] == ["st8"]
    assert q["redirect_uri"] == ["http://localhost:8765/callback"]
    assert q.get("client_id", q.get("client_key")) in (["tw"], ["g"], ["tk"], ["m"])


@respx.mock
async def test_youtube_token_endpoint_outage_is_not_auth_error(tmp_path):
    respx.post(UPLOAD_URL).mock(return_value=httpx.Response(401))
    respx.post(GOOGLE_TOKEN).mock(return_value=httpx.Response(503, text="backend error"))
    pub = YouTubePublisher(S, _tokens(tmp_path, "youtube", {"access_token": "a", "refresh_token": "r"}),
                           httpx.AsyncClient())
    with pytest.raises(RuntimeError) as e:
        await pub.publish(_video(tmp_path), META)
    assert not isinstance(e.value, AuthError)


@respx.mock
async def test_tiktok_token_endpoint_outage_is_not_auth_error(tmp_path):
    respx.post(f"{TT}/v2/post/publish/creator_info/query/").mock(return_value=httpx.Response(401, json={}))
    respx.post(f"{TT}/v2/oauth/token/").mock(return_value=httpx.Response(500, text="oops"))
    pub = TikTokPublisher(S, _tokens(tmp_path, "tiktok", {"access_token": "a", "refresh_token": "r"}),
                          httpx.AsyncClient(), sleep=_nosleep)
    with pytest.raises(RuntimeError) as e:
        await pub.publish(_video(tmp_path), META)
    assert not isinstance(e.value, AuthError)


@respx.mock
@pytest.mark.parametrize("code,msg", [(4, "Application request limit reached"), (100, "Invalid parameter")])
async def test_instagram_non_token_oauth_exception_is_not_auth_error(tmp_path, code, msg):
    v = Settings().graph_api_version
    respx.post(f"{GRAPH}/{v}/IG1/media").mock(return_value=httpx.Response(
        400, json={"error": {"type": "OAuthException", "code": code, "message": msg}}))
    pub = InstagramPublisher(S, _tokens(tmp_path, "instagram", {"page_token": "pt", "ig_user_id": "IG1"}),
                             httpx.AsyncClient(), sleep=_nosleep)
    with pytest.raises(RuntimeError) as e:
        await pub.publish(_video(tmp_path), META)
    assert not isinstance(e.value, AuthError)
