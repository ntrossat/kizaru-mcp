import asyncio
import time

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from fakeredis import FakeAsyncRedis
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AuthorizationParams
from mcp.server.mcpserver.exceptions import ToolError
from starlette.requests import Request

from lightdash_mcp.auth.provider import (
    Access,
    Grant,
    LightdashOAuthProvider,
    Refresh,
    SignInRequired,
    Transaction,
    _consent_cookie,
)
from lightdash_mcp.auth.store import Store, digest
from lightdash_mcp.config import Settings
from lightdash_mcp.tools.common import RECONNECT, lightdash

LIGHTDASH = "http://lightdash.test"
TOKEN_URL = f"{LIGHTDASH}/api/v1/oauth/token"


@pytest.fixture
def provider() -> LightdashOAuthProvider:
    settings = Settings(
        _env_file=None, lightdash_url=LIGHTDASH, lightdash_client_id="id", lightdash_client_secret="secret", fernet_key=Fernet.generate_key().decode()
    )
    return LightdashOAuthProvider(settings, Store(FakeAsyncRedis(), settings.fernet_key))


async def add_grant(provider: LightdashOAuthProvider, expires_in: float, grant_id: str = "grant") -> str:
    access = f"our-access-{grant_id}"
    grant = Grant(
        client_id="client",
        subject="user",
        access_token=f"ld-access-{grant_id}",
        refresh_token=f"ld-refresh-{grant_id}",
        expires_at=time.time() + expires_in,
        access_digest=digest(access),
    )
    await provider.store.put("grant", grant_id, grant)
    await provider.store.put(
        "access", digest(access), Access(token=access, client_id="client", scopes=[], subject="user", grant_id=grant_id)
    )
    return access


def signed_in_as(access: Access):
    return auth_context_var.set(AuthenticatedUser(access))


async def test_stored_values_are_encrypted(provider):
    await add_grant(provider, 3600)
    raw = await provider.store._redis.get("lightdash-mcp:grant:grant")
    assert b"ld-refresh" not in raw


async def test_values_from_another_key_count_as_missing(provider):
    access = await add_grant(provider, 3600)
    other = Store(provider.store._redis, Fernet.generate_key().decode())
    assert await other.get("access", digest(access), Access) is None
    assert await other.pop("grant", "grant", Grant) is None


async def test_fresh_token_is_used_as_is(provider):
    await add_grant(provider, 3600)
    assert await provider.lightdash_token("grant") == "ld-access-grant"


@respx.mock
async def test_concurrent_requests_refresh_once(provider):
    await add_grant(provider, 10)
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "ld-access-2", "refresh_token": "ld-refresh-2", "expires_in": 3600})
    )
    tokens = await asyncio.gather(*(provider.lightdash_token("grant") for _ in range(5)))
    assert tokens == ["ld-access-2"] * 5
    assert route.call_count == 1
    assert b"refresh_token=ld-refresh-grant" in route.calls[0].request.content
    grant = await provider.store.get("grant", "grant", Grant)
    assert grant.refresh_token == "ld-refresh-2"


@respx.mock
async def test_refused_refresh_ends_the_sign_in(provider):
    access = await add_grant(provider, 10)
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(401, json={"error": "invalid_grant"}))
    with pytest.raises(SignInRequired):
        await provider.lightdash_token("grant")
    assert await provider.store.get("grant", "grant", Grant) is None
    assert await provider.load_access_token(access) is None


async def test_access_token_is_tied_to_its_grant(provider):
    access = await add_grant(provider, 3600)
    assert (await provider.load_access_token(access)).subject == "user"
    await provider.end_grant("grant")
    assert await provider.load_access_token(access) is None


@respx.mock
async def test_revoke_ends_the_grant_upstream_too(provider):
    access = await add_grant(provider, 3600)
    revoke = respx.post(f"{LIGHTDASH}/api/v1/oauth/revoke").mock(return_value=httpx.Response(200))
    await provider.revoke_token(await provider.load_access_token(access))
    assert await provider.load_access_token(access) is None
    assert b"token=ld-refresh-grant" in revoke.calls[0].request.content


@respx.mock
async def test_tools_map_lightdash_errors(provider):
    access = await add_grant(provider, 3600)
    reset = signed_in_as(await provider.load_access_token(access))
    try:
        respx.get(f"{LIGHTDASH}/api/v1/org").mock(
            return_value=httpx.Response(403, json={"status": "error", "error": {"message": "Not allowed"}})
        )
        with pytest.raises(ToolError, match="Permission denied.*Not allowed"):
            async with lightdash(provider) as ld:
                await ld.get("/api/v1/org")

        respx.get(f"{LIGHTDASH}/api/v1/org").mock(return_value=httpx.Response(401))
        with pytest.raises(ToolError, match=RECONNECT):
            async with lightdash(provider) as ld:
                await ld.get("/api/v1/org")
        assert await provider.load_access_token(access) is None
    finally:
        auth_context_var.reset(reset)


async def test_tools_require_a_sign_in(provider):
    with pytest.raises(ToolError, match="Not signed in"):
        async with lightdash(provider):
            pass


async def test_grants_stay_separate(provider):
    first = await add_grant(provider, 3600, "first")
    second = await add_grant(provider, 3600, "second")
    await provider.end_grant("first")
    assert await provider.load_access_token(first) is None
    assert (await provider.load_access_token(second)).grant_id == "second"
    assert await provider.lightdash_token("second") == "ld-access-second"


@respx.mock
async def test_refresh_token_survives_lightdash_being_down(provider):
    await add_grant(provider, 3600)
    refresh = Refresh(token="our-refresh", client_id="client", scopes=[], expires_at=int(time.time()) + 600, grant_id="grant")
    await provider.store.put("refresh", digest(refresh.token), refresh)
    respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(httpx.ConnectError):
        await provider.exchange_refresh_token(None, refresh, [])
    assert await provider.store.get("refresh", digest(refresh.token), Refresh) == refresh

    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "ld-access-2", "refresh_token": "ld-refresh-2", "expires_in": 3600})
    )
    token = await provider.exchange_refresh_token(None, refresh, [])
    assert await provider.load_access_token(token.access_token)
    assert await provider.store.get("refresh", digest(refresh.token), Refresh) is None


@respx.mock
async def test_server_side_refresh_errors_keep_the_sign_in(provider):
    access = await add_grant(provider, 10)
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(401, json={"error": "invalid_client"}))
    with pytest.raises(httpx.HTTPStatusError):
        await provider.lightdash_token("grant")
    assert await provider.load_access_token(access)


@respx.mock
async def test_revoke_waits_for_a_refresh_in_flight(provider):
    access = await add_grant(provider, 10)
    refreshing, finish = asyncio.Event(), asyncio.Event()

    async def slow_refresh(request):
        refreshing.set()
        await finish.wait()
        return httpx.Response(200, json={"access_token": "ld-access-2", "refresh_token": "ld-refresh-2", "expires_in": 3600})

    respx.post(TOKEN_URL).mock(side_effect=slow_refresh)
    revoke = respx.post(f"{LIGHTDASH}/api/v1/oauth/revoke").mock(return_value=httpx.Response(200))
    refresh = asyncio.create_task(provider.lightdash_token("grant"))
    await refreshing.wait()
    revoked = asyncio.create_task(provider.revoke_token(await provider.load_access_token(access)))
    await asyncio.sleep(0.05)
    finish.set()
    await asyncio.gather(refresh, revoked)

    assert await provider.store.get("grant", "grant", Grant) is None
    assert b"token=ld-refresh-2" in revoke.calls[0].request.content


@respx.mock
async def test_failed_callback_returns_to_the_client(provider):
    transaction = Transaction(
        client_id="client",
        params=AuthorizationParams(
            state="client-state",
            scopes=[],
            code_challenge="x" * 43,
            redirect_uri="http://localhost:9999/callback",
            redirect_uri_provided_explicitly=True,
        ),
        verifier="verifier",
        csrf="csrf",
        approved=True,
    )
    await provider.store.put("transaction", "t", transaction)
    respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("down"))
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/oauth/lightdash/callback",
            "query_string": b"state=t&code=lightdash-code",
            "headers": [(b"cookie", f"{_consent_cookie('t')}=csrf".encode())],
        }
    )
    response = await provider.lightdash_callback(request)
    assert response.status_code == 302
    assert response.headers["location"].startswith("http://localhost:9999/callback?error=server_error")
