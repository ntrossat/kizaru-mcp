"""Sign-in, refresh and revocation through the running server."""

import httpx

from .conftest import ADMIN, VIEWER, allow, authorize, exchange, lightdash_sign_in, register_client, sign_in, start


def mcp_status(server: str, access_token: str) -> int:
    """Status of an MCP initialize request with this token: 401 when the token is not accepted."""
    response = httpx.post(
        f"{server}/mcp",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
    )
    return response.status_code


def refresh(server: str, token: dict) -> httpx.Response:
    client = token["client"]
    return httpx.post(
        f"{server}/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "resource": f"{server}/mcp",
        },
    )


def test_unauthenticated_request_is_refused(server):
    assert mcp_status(server, "not-a-token") == 401
    metadata = httpx.get(f"{server}/.well-known/oauth-authorization-server").json()
    assert metadata["registration_endpoint"] == f"{server}/register"


def test_consent_requires_the_cookie(server):
    client = register_client(server)
    with httpx.Client(follow_redirects=False) as browser:
        authorize = browser.get(
            f"{server}/authorize",
            params={"response_type": "code", "client_id": client["client_id"], "redirect_uri": "http://localhost:9999/callback",
                    "code_challenge": "x" * 43, "code_challenge_method": "S256"},
        )
        page = browser.get(authorize.headers["location"])
        assert "test client" in page.text
        transaction = authorize.headers["location"].split("transaction=")[1]
    # A cross-site form post carries no cookie.
    forged = httpx.post(f"{server}/oauth/consent", data={"transaction": transaction, "csrf": "guess", "action": "allow"})
    assert forged.status_code == 400


def test_sign_in_finishes_only_in_the_browser_that_consented(server):
    attacker = register_client(server, "attacker")
    with httpx.Client(follow_redirects=False, timeout=30) as attacker_browser:
        to_lightdash = allow(attacker_browser, start(attacker_browser, server, attacker, "v" * 43))
    with httpx.Client(follow_redirects=False, timeout=30) as victim_browser:
        callback = victim_browser.get(lightdash_sign_in(victim_browser, ADMIN, to_lightdash))
    assert callback.status_code == 400
    assert "location" not in callback.headers


def test_two_consent_pages_in_one_browser(server):
    first, second = register_client(server, "first"), register_client(server, "second")
    with httpx.Client(follow_redirects=False, timeout=30) as browser:
        first_page = start(browser, server, first, "v" * 43)
        second_page = start(browser, server, second, "v" * 43)
        assert allow(browser, first_page).status_code == 303
        assert allow(browser, second_page).status_code == 303


def test_code_needs_the_verifier_and_works_once(server):
    client = register_client(server)
    code, verifier = authorize(server, ADMIN, client)
    assert exchange(server, client, code, "wrong-verifier-" + "x" * 30).status_code == 400
    assert exchange(server, client, code, verifier).status_code == 200
    assert exchange(server, client, code, verifier).status_code == 400


async def test_refresh_rotates_and_revoke_ends_the_sign_in(server, tool):
    token = sign_in(server, ADMIN)
    rotated = refresh(server, token)
    assert rotated.status_code == 200, rotated.text
    new = {**rotated.json(), "client": token["client"]}

    assert mcp_status(server, token["access_token"]) == 401
    assert refresh(server, token).status_code == 400  # a refresh token works once
    assert not (await tool(new, "list_projects")).is_error

    revoked = httpx.post(
        f"{server}/revoke",
        data={"token": new["refresh_token"], "client_id": token["client"]["client_id"], "client_secret": token["client"]["client_secret"]},
    )
    assert revoked.status_code == 200
    assert mcp_status(server, new["access_token"]) == 401
    assert refresh(server, new).status_code == 400


async def test_sign_ins_stay_separate(server, tool):
    admin_a, admin_b, viewer = sign_in(server, ADMIN), sign_in(server, ADMIN), sign_in(server, VIEWER)
    assert not (await tool(admin_a, "list_roles")).is_error
    assert (await tool(viewer, "list_roles")).is_error

    httpx.post(
        f"{server}/revoke",
        data={"token": admin_a["access_token"], "client_id": admin_a["client"]["client_id"], "client_secret": admin_a["client"]["client_secret"]},
    )
    assert mcp_status(server, admin_a["access_token"]) == 401
    assert not (await tool(admin_b, "list_roles")).is_error


def test_a_client_cannot_use_another_clients_refresh_token(server):
    token = sign_in(server, ADMIN)
    other = register_client(server, "other client")
    response = httpx.post(
        f"{server}/token",
        data={"grant_type": "refresh_token", "refresh_token": token["refresh_token"], "client_id": other["client_id"], "client_secret": other["client_secret"]},
    )
    assert response.status_code == 400
