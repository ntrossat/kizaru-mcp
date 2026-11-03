"""Runs against the local Lightdash from `make dev` (http://localhost:8080) and Redis (db 15).

The server runs in a thread on PUBLIC_PORT. Sign-in goes through the whole chain: client
registration, authorize, consent page, Lightdash login and consent, callback, token.
"""

import html
import re
import secrets
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import httpx2
import pytest
import uvicorn
from cryptography.fernet import Fernet
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from redis.asyncio import Redis

from kizaru_mcp.auth.provider import _challenge
from kizaru_mcp.config import Settings
from kizaru_mcp.server import create_server, transport_security

LIGHTDASH = "http://localhost:8080"
PUBLIC_PORT = 8765
PUBLIC = f"http://localhost:{PUBLIC_PORT}"
CLIENT_REDIRECT = "http://localhost:9999/callback"
PASSWORD = "demo_password!"
ADMIN, EDITOR, VIEWER = "demo@lightdash.com", "demo2@lightdash.com", "demo3@lightdash.com"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    try:
        httpx.get(f"{LIGHTDASH}/api/v1/health", timeout=3).raise_for_status()
    except httpx.HTTPError:
        for item in items:
            if "integration" in str(item.path):
                item.add_marker(pytest.mark.skip(reason="Lightdash is not running: make setup"))


@pytest.fixture(scope="session")
def settings() -> Settings:
    registered = httpx.post(
        f"{LIGHTDASH}/api/v1/oauth/register",
        json={
            "client_name": "kizaru-mcp-tests",
            "redirect_uris": [f"{PUBLIC}/oauth/lightdash/callback"],
            "scope": "read write",
        },
    ).json()
    return Settings(
        _env_file=None,
        lightdash_url=LIGHTDASH,
        lightdash_client_id=registered["client_id"],
        lightdash_client_secret=registered["client_secret"],
        public_url=PUBLIC,
        fernet_key=Fernet.generate_key().decode(),
        redis_url="redis://localhost:6379/15",
        port=PUBLIC_PORT,
    )


@pytest.fixture(scope="session")
def server(settings: Settings):
    app = create_server(settings, Redis.from_url(settings.redis_url)).streamable_http_app(
        transport_security=transport_security(settings)
    )
    instance = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PUBLIC_PORT, log_level="warning"))
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()
    for _ in range(100):
        if instance.started:
            break
        time.sleep(0.05)
    yield PUBLIC
    instance.should_exit = True
    thread.join(5)


def register_client(server: str, name: str = "test client") -> dict[str, Any]:
    response = httpx.post(
        f"{server}/register",
        json={"client_name": name, "redirect_uris": [CLIENT_REDIRECT], "token_endpoint_auth_method": "client_secret_post"},
    )
    response.raise_for_status()
    return response.json()


def start(browser: httpx.Client, server: str, client: dict[str, Any], verifier: str) -> httpx.Response:
    """The MCP client's /authorize, opened in the browser. Returns the consent page."""
    authorize = browser.get(
        f"{server}/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": CLIENT_REDIRECT,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "state": "client-state",
            "resource": f"{server}/mcp",
        },
    )
    return browser.get(authorize.headers["location"])


def allow(browser: httpx.Client, consent: httpx.Response) -> httpx.Response:
    """Clicks Continue on the consent page. Returns the redirect to Lightdash."""
    fields = dict(re.findall(r'name="(transaction|csrf)" value="([^"]*)"', consent.text))
    return browser.post(consent.url, data={**fields, "action": "allow"})


def lightdash_sign_in(browser: httpx.Client, email: str, to_lightdash: httpx.Response) -> str:
    """Signs in to Lightdash and approves. Returns the callback URL Lightdash sends the browser to."""
    browser.post(f"{LIGHTDASH}/api/v1/login", json={"email": email, "password": PASSWORD}).raise_for_status()
    page = browser.get(to_lightdash.headers["location"])
    hidden = {k: html.unescape(v) for k, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', page.text)}
    redirect = browser.post(f"{LIGHTDASH}/api/v1/oauth/authorize", data={**hidden, "approve": "true"})
    return html.unescape(re.search(r'url=([^"]+)"', redirect.text).group(1))


def authorize(server: str, email: str, client: dict[str, Any]) -> tuple[str, str]:
    """The MCP client's authorization, with the user's clicks done over HTTP. Returns the code and PKCE verifier."""
    verifier = secrets.token_urlsafe(48)
    with httpx.Client(follow_redirects=False, timeout=30) as browser:
        to_lightdash = allow(browser, start(browser, server, client, verifier))
        to_client = browser.get(lightdash_sign_in(browser, email, to_lightdash))
        query = parse_qs(urlparse(to_client.headers["location"]).query)
        assert query["state"] == ["client-state"], query
    return query["code"][0], verifier


def exchange(server: str, client: dict[str, Any], code: str, verifier: str) -> httpx.Response:
    return httpx.post(
        f"{server}/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": CLIENT_REDIRECT,
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "code_verifier": verifier,
            "resource": f"{server}/mcp",
        },
    )


def sign_in(server: str, email: str, client: dict[str, Any] | None = None) -> dict[str, Any]:
    """Registration, authorization and token exchange. Returns the token response."""
    client = client or register_client(server)
    token = exchange(server, client, *authorize(server, email, client))
    token.raise_for_status()
    return {**token.json(), "client": client}


async def call(server: str, access_token: str, tool: str, arguments: dict[str, Any] | None = None):
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {access_token}"}, timeout=120)
    async with Client(streamable_http_client(f"{server}/mcp", http_client=http)) as client:
        return await client.call_tool(tool, arguments or {})


@pytest.fixture(scope="session")
def admin(server: str) -> dict[str, Any]:
    return sign_in(server, ADMIN)


@pytest.fixture(scope="session")
def viewer(server: str) -> dict[str, Any]:
    return sign_in(server, VIEWER)


@pytest.fixture(scope="session")
def lightdash_admin() -> httpx.Client:
    """Lightdash REST as the admin, with a session cookie, to set up and check test data."""
    client = httpx.Client(base_url=LIGHTDASH, timeout=60)
    client.post("/api/v1/login", json={"email": ADMIN, "password": PASSWORD}).raise_for_status()
    return client


@pytest.fixture(scope="session")
def project_uuid(lightdash_admin: httpx.Client) -> str:
    return lightdash_admin.get("/api/v1/org/projects").json()["results"][0]["projectUuid"]


@pytest.fixture(scope="session")
def tool(server: str):
    """Calls a tool as the holder of an access token."""

    async def run(token: dict[str, Any], name: str, arguments: dict[str, Any] | None = None):
        return await call(server, token["access_token"], name, arguments)

    return run
