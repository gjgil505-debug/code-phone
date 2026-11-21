import httpx
import pytest
import respx

from clipbot.config import Settings
from clipbot.oauth import AuthSetupError, exchange_code, parse_redirect

S = Settings(twitch_client_id="tw", twitch_client_secret="tws", meta_app_id="m", meta_app_secret="ms")
REDIR = "http://localhost:8765/callback"


def test_parse_redirect_checks_state():
    assert parse_redirect(f"{REDIR}?code=abc&state=s1", "s1") == "abc"
    with pytest.raises(AuthSetupError):
        parse_redirect(f"{REDIR}?code=abc&state=evil", "s1")
    with pytest.raises(AuthSetupError, match="access_denied"):
        parse_redirect(f"{REDIR}?error=access_denied&state=s1", "s1")


@respx.mock
async def test_exchange_twitch():
    route = respx.post("https://id.twitch.tv/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "scope": ["clips:edit"]}))
    tok = await exchange_code("twitch", S, "c0de", REDIR, httpx.AsyncClient())
    assert tok == {"access_token": "a", "refresh_token": "r"}
    assert b"grant_type=authorization_code" in route.calls[0].request.content


@respx.mock
async def test_exchange_instagram_picks_page_with_ig_account():
    v = S.graph_api_version
    respx.get(f"https://graph.facebook.com/{v}/oauth/access_token").mock(side_effect=[
        httpx.Response(200, json={"access_token": "short"}),
        httpx.Response(200, json={"access_token": "long"}),
    ])
    respx.get(f"https://graph.facebook.com/{v}/me/accounts").mock(return_value=httpx.Response(200, json={"data": [
        {"name": "No IG", "access_token": "p0"},
        {"name": "Clips Page", "access_token": "p1", "instagram_business_account": {"id": "IG9"}},
    ]}))
    tok = await exchange_code("instagram", S, "c", REDIR, httpx.AsyncClient())
    assert tok == {"page_token": "p1", "ig_user_id": "IG9", "page_name": "Clips Page"}


@respx.mock
async def test_exchange_instagram_without_linked_account_errors():
    v = S.graph_api_version
    respx.get(f"https://graph.facebook.com/{v}/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "t"}))
    respx.get(f"https://graph.facebook.com/{v}/me/accounts").mock(
        return_value=httpx.Response(200, json={"data": [{"name": "x", "access_token": "p"}]}))
    with pytest.raises(AuthSetupError, match="Instagram"):
        await exchange_code("instagram", S, "c", REDIR, httpx.AsyncClient())


def test_paste_mode_on_servers_and_phones():
    from clipbot.oauth import use_paste_mode
    local = "http://localhost:8765/callback"
    assert use_paste_mode(local, {}) is False                      # desktop: browser on same machine
    assert use_paste_mode(local, {"SSH_CONNECTION": "1.2.3.4 5 6 7"}) is True  # logged in over SSH (Termius)
    assert use_paste_mode(local, {"CLIPBOT_PASTE_LOGIN": "1"}) is True
    assert use_paste_mode("https://example.com/cb", {}) is True    # redirect page isn't this machine
