"""LightdashOAuthProvider: the MCP server's own OAuth server, proxying sign-in to Lightdash.

MCP clients register here and get this server's tokens. Each sign-in is a grant that holds
the user's Lightdash tokens, encrypted in Redis. Tools call Lightdash with the grant's token,
refreshed under a lock so a rotated refresh token is never used twice.
"""

import base64
import hashlib
import html
import secrets
import time
from urllib.parse import urlencode, urlparse

import httpx
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from kizaru_mcp.auth.store import Store, digest
from kizaru_mcp.config import Settings

SCOPE = "lightdash"
LIGHTDASH_SCOPE = "read write"
TRANSACTION_TTL = 10 * 60
CODE_TTL = 5 * 60
ACCESS_TTL = 60 * 60
REFRESH_TTL = 14 * 24 * 60 * 60  # Lightdash's refresh-token lifetime
REFRESH_MARGIN = 60
CLIENT_TTL = 30 * 24 * 60 * 60  # renewed on use: registration is open, so unused clients must expire
CONSENT_COOKIE = "kizaru_mcp_consent"  # one per transaction, suffixed with its digest


class SignInRequired(Exception):
    """The user's Lightdash sign-in ended: they must reconnect."""


class Transaction(BaseModel):
    """A pending authorization, from the client's request to the Lightdash callback."""

    client_id: str
    params: AuthorizationParams
    verifier: str
    csrf: str = ""
    approved: bool = False


class Grant(BaseModel):
    """One sign-in: the user's Lightdash tokens and this server's current tokens for it."""

    client_id: str
    subject: str
    access_token: str
    refresh_token: str
    expires_at: float
    access_digest: str = ""
    refresh_digest: str = ""


class Code(AuthorizationCode):
    grant_id: str


class Access(AccessToken):
    grant_id: str


class Refresh(RefreshToken):
    grant_id: str


def _consent_cookie(transaction_id: str) -> str:
    return f"{CONSENT_COOKIE}_{digest(transaction_id)[:16]}"


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


class LightdashOAuthProvider:
    def __init__(self, settings: Settings, store: Store) -> None:
        self.settings = settings
        self.store = store
        self._http = httpx.AsyncClient(base_url=settings.lightdash_url, timeout=30)

    # Client registration

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        client = await self.store.get("client", client_id, OAuthClientInformationFull)
        if client:
            await self.store.touch("client", client_id, CLIENT_TTL)
        return client

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await self.store.put("client", client_info.client_id, client_info, CLIENT_TTL)

    # Authorization: client -> consent page -> Lightdash -> callback -> client

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        transaction_id = secrets.token_urlsafe(32)
        transaction = Transaction(client_id=client.client_id, params=params, verifier=secrets.token_urlsafe(48))
        await self.store.put("transaction", transaction_id, transaction, TRANSACTION_TTL)
        return f"{self.settings.public_url}/oauth/consent?{urlencode({'transaction': transaction_id})}"

    async def consent_page(self, request: Request) -> Response:
        transaction_id = request.query_params.get("transaction", "")
        transaction = await self.store.get("transaction", transaction_id, Transaction)
        client = transaction and await self.get_client(transaction.client_id)
        if not transaction or not client:
            return _page("Sign-in expired", "<p>Start again from your MCP client.</p>", status=400)

        transaction.csrf = secrets.token_urlsafe(32)
        await self.store.put("transaction", transaction_id, transaction, TRANSACTION_TTL)
        client_name = html.escape(client.client_name or client.client_id)
        redirect_uri = urlparse(str(transaction.params.redirect_uri))
        # A custom scheme, such as myapp://, has no host to show: show the whole address instead.
        destination = html.escape(redirect_uri.netloc if redirect_uri.scheme in ("http", "https") else redirect_uri.geturl())
        body = f"""
            <p><strong>{client_name}</strong> wants to use Lightdash as you.</p>
            <p class="muted">It will act with your Lightdash permissions. You'll return to <strong>{destination}</strong>.</p>
            <form method="post">
              <input type="hidden" name="transaction" value="{html.escape(transaction_id)}">
              <input type="hidden" name="csrf" value="{transaction.csrf}">
              <button name="action" value="deny" class="secondary">Cancel</button>
              <button name="action" value="allow">Continue to Lightdash</button>
            </form>"""
        response = _page("Connect to Lightdash", body)
        response.set_cookie(
            _consent_cookie(transaction_id),
            transaction.csrf,
            max_age=TRANSACTION_TTL,
            path="/oauth",
            httponly=True,
            samesite="lax",
            secure=self._secure(request),
        )
        return response

    def _secure(self, request: Request) -> bool:
        """Behind a tunnel or proxy the request may look like plain HTTP: PUBLIC_URL says what browsers use."""
        return self.settings.public_url.startswith("https://") or request.url.scheme == "https"

    async def consent_submit(self, request: Request) -> Response:
        form = await request.form()
        transaction_id = str(form.get("transaction", ""))
        transaction = await self.store.get("transaction", transaction_id, Transaction)
        csrf = str(form.get("csrf", ""))
        if (
            not transaction
            or not transaction.csrf
            or not secrets.compare_digest(csrf, transaction.csrf)
            or not secrets.compare_digest(request.cookies.get(_consent_cookie(transaction_id), ""), transaction.csrf)
        ):
            return _page("Sign-in expired", "<p>Start again from your MCP client.</p>", status=400)

        if form.get("action") != "allow":
            await self.store.delete("transaction", transaction_id)
            response = _redirect_to_client(transaction, error="access_denied")
            response.delete_cookie(_consent_cookie(transaction_id), path="/oauth", secure=self._secure(request))
            return response

        transaction.approved = True
        await self.store.put("transaction", transaction_id, transaction, TRANSACTION_TTL)

        query = {
            "response_type": "code",
            "client_id": self.settings.lightdash_client_id,
            "redirect_uri": self.settings.callback_url,
            "scope": LIGHTDASH_SCOPE,
            "state": transaction_id,
            "code_challenge": _challenge(transaction.verifier),
            "code_challenge_method": "S256",
        }
        # The consent cookie stays until the callback: it ties the sign-in to this browser.
        return RedirectResponse(f"{self.settings.lightdash_url}/api/v1/oauth/authorize?{urlencode(query)}", 303)

    async def lightdash_callback(self, request: Request) -> Response:
        transaction_id = request.query_params.get("state", "")
        transaction = await self.store.get("transaction", transaction_id, Transaction)
        # Only the browser that approved the consent page can finish the sign-in, so a Lightdash link
        # taken from someone else's consent can't send this user's code to their client.
        if (
            not transaction
            or not transaction.approved
            or not secrets.compare_digest(request.cookies.get(_consent_cookie(transaction_id), ""), transaction.csrf)
            or not await self.store.pop("transaction", transaction_id, Transaction)
        ):
            return _page("Sign-in expired", "<p>Start again from your MCP client, in this browser.</p>", status=400)

        response = await self._finish_sign_in(transaction, request.query_params.get("code"), request.query_params.get("error"))
        response.delete_cookie(_consent_cookie(transaction_id), path="/oauth", secure=self._secure(request))
        return response

    async def _finish_sign_in(self, transaction: Transaction, code: str | None, error: str | None) -> Response:
        if error or not code:
            return _redirect_to_client(transaction, error=error or "access_denied")
        try:
            grant_id, grant = await self._create_grant(transaction, code)
        except httpx.HTTPError, ValueError, KeyError:
            return _redirect_to_client(transaction, error="server_error", description="Lightdash sign-in failed")

        code = secrets.token_urlsafe(32)
        params = transaction.params
        await self.store.put(
            "code",
            digest(code),
            Code(
                code=code,
                scopes=params.scopes or [],
                expires_at=time.time() + CODE_TTL,
                client_id=transaction.client_id,
                code_challenge=params.code_challenge,
                redirect_uri=params.redirect_uri,
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                resource=params.resource,
                subject=grant.subject,
                grant_id=grant_id,
            ),
            CODE_TTL,
        )
        return RedirectResponse(construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state), 302)

    async def _create_grant(self, transaction: Transaction, code: str) -> tuple[str, Grant]:
        response = await self._http.post(
            "/api/v1/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.settings.callback_url,
                "client_id": self.settings.lightdash_client_id,
                "client_secret": self.settings.lightdash_client_secret,
                "code_verifier": transaction.verifier,
            },
        )
        response.raise_for_status()
        tokens = response.json()
        user = await self._http.get("/api/v1/user", headers={"Authorization": f"Bearer {tokens['access_token']}"})
        user.raise_for_status()

        grant_id = secrets.token_urlsafe(16)
        grant = Grant(
            client_id=transaction.client_id,
            subject=user.json()["results"]["userUuid"],
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            expires_at=time.time() + tokens.get("expires_in", ACCESS_TTL),
        )
        await self.store.put("grant", grant_id, grant, REFRESH_TTL)
        return grant_id, grant

    # Tokens

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> Code | None:
        code = await self.store.get("code", digest(authorization_code), Code)
        return code if code and _same(code.code, authorization_code) and code.client_id == client.client_id else None

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: Code) -> OAuthToken:
        if not await self.store.pop("code", digest(authorization_code.code), Code):
            raise TokenError("invalid_grant", "Authorization code already used")
        return await self._issue(authorization_code.grant_id, authorization_code.scopes, authorization_code.resource)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> Refresh | None:
        token = await self.store.get("refresh", digest(refresh_token), Refresh)
        return token if token and _same(token.token, refresh_token) and token.client_id == client.client_id else None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: Refresh, scopes: list[str]
    ) -> OAuthToken:
        if not await self.store.pop("refresh", digest(refresh_token.token), Refresh):
            raise TokenError("invalid_grant", "Refresh token already used")
        try:
            # Keeps the Lightdash sign-in alive as long as the client's, and catches a revoked one now.
            await self.lightdash_token(refresh_token.grant_id, force_refresh=True)
        except SignInRequired:
            raise TokenError("invalid_grant", "Lightdash sign-in ended") from None
        except Exception:
            # Lightdash unreachable: give the refresh token back so the client can retry.
            ttl = int(refresh_token.expires_at - time.time()) if refresh_token.expires_at else REFRESH_TTL
            await self.store.put("refresh", digest(refresh_token.token), refresh_token, ttl)
            raise
        return await self._issue(refresh_token.grant_id, scopes or refresh_token.scopes, refresh_token.resource)

    async def load_access_token(self, token: str) -> Access | None:
        access = await self.store.get("access", digest(token), Access)
        if not access or not _same(access.token, token) or (access.expires_at and access.expires_at < time.time()):
            return None
        grant = await self.store.get("grant", access.grant_id, Grant)
        return access if grant and grant.access_digest == digest(token) else None

    async def revoke_token(self, token: Access | Refresh) -> None:
        await self.end_grant(token.grant_id, revoke_upstream=True)

    async def _issue(self, grant_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        async with self.store.lock("grant", grant_id):
            grant = await self.store.get("grant", grant_id, Grant)
            if not grant:
                raise TokenError("invalid_grant", "Sign-in ended")
            access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            common = {
                "client_id": grant.client_id,
                "scopes": scopes,
                "resource": resource,
                "subject": grant.subject,
                "grant_id": grant_id,
            }
            await self.store.put(
                "access", digest(access), Access(token=access, expires_at=int(time.time()) + ACCESS_TTL, **common), ACCESS_TTL
            )
            await self.store.put(
                "refresh",
                digest(refresh),
                Refresh(token=refresh, expires_at=int(time.time()) + REFRESH_TTL, **common),
                REFRESH_TTL,
            )
            await self.store.delete("access", grant.access_digest)
            await self.store.delete("refresh", grant.refresh_digest)
            grant.access_digest, grant.refresh_digest = digest(access), digest(refresh)
            await self.store.put("grant", grant_id, grant, REFRESH_TTL)
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TTL,
            refresh_token=refresh,
            scope=" ".join(scopes) or None,
        )

    # Lightdash tokens

    async def lightdash_token(self, grant_id: str, force_refresh: bool = False) -> str:
        """The grant's Lightdash access token, refreshed first if it is about to expire."""
        grant = await self.store.get("grant", grant_id, Grant)
        if not grant:
            raise SignInRequired
        if not force_refresh and grant.expires_at - time.time() > REFRESH_MARGIN:
            return grant.access_token

        async with self.store.lock("grant", grant_id):
            stale = grant.refresh_token
            grant = await self.store.get("grant", grant_id, Grant)
            if not grant:
                raise SignInRequired
            if grant.refresh_token != stale or (not force_refresh and grant.expires_at - time.time() > REFRESH_MARGIN):
                return grant.access_token  # refreshed meanwhile by another request

            response = await self._http.post(
                "/api/v1/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": grant.refresh_token,
                    "client_id": self.settings.lightdash_client_id,
                    "client_secret": self.settings.lightdash_client_secret,
                },
            )
            # Only a refused grant ends the sign-in. Other errors, such as invalid_client, are the server's.
            if response.status_code in (400, 401) and _oauth_error(response) == "invalid_grant":
                await self._end_grant(grant_id)
                raise SignInRequired
            response.raise_for_status()
            tokens = response.json()
            grant.access_token = tokens["access_token"]
            grant.refresh_token = tokens["refresh_token"]
            grant.expires_at = time.time() + tokens.get("expires_in", ACCESS_TTL)
            # Saved before use: Lightdash has already rotated the old refresh token.
            await self.store.put("grant", grant_id, grant, REFRESH_TTL)
            return grant.access_token

    async def end_grant(self, grant_id: str, revoke_upstream: bool = False) -> None:
        # Under the grant's lock, so a refresh or token exchange in flight can't put the grant back.
        async with self.store.lock("grant", grant_id):
            grant = await self._end_grant(grant_id)
        if grant and revoke_upstream:
            try:
                await self._http.post("/api/v1/oauth/revoke", data={"token": grant.refresh_token})
            except httpx.HTTPError:
                pass  # this server's tokens are gone either way

    async def _end_grant(self, grant_id: str) -> Grant | None:
        """Ends the grant and its tokens. The caller holds the grant's lock."""
        grant = await self.store.pop("grant", grant_id, Grant)
        if grant:
            await self.store.delete("access", grant.access_digest)
            await self.store.delete("refresh", grant.refresh_digest)
        return grant


def _same(stored: str, given: str) -> bool:
    """A stored token is the one it was looked up by, not a value copied under its key in Redis."""
    return secrets.compare_digest(stored.encode(), given.encode())


def _oauth_error(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("error") if isinstance(body, dict) else None


def _redirect_to_client(transaction: Transaction, error: str, description: str | None = None) -> Response:
    url = construct_redirect_uri(
        str(transaction.params.redirect_uri), error=error, error_description=description, state=transaction.params.state
    )
    return RedirectResponse(url, 302)


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; --bg: #f6f7f9; --card: #fff; --text: #16181d; --muted: #5f6673; --accent: #7262ff; --line: #e3e5ea; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #111317; --card: #1a1d23; --text: #eceef2; --muted: #9aa1ad; --line: #2b2f37; }} }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--bg); color: var(--text);
         font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 16px; box-sizing: border-box; }}
  main {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 28px; max-width: 420px; width: 100%; }}
  h1 {{ font-size: 18px; margin: 0 0 16px; }}
  .muted {{ color: var(--muted); }}
  form {{ display: flex; gap: 8px; justify-content: flex-end; margin-top: 24px; }}
  button {{ font: inherit; border-radius: 8px; padding: 8px 14px; border: 1px solid var(--accent); background: var(--accent); color: #fff; cursor: pointer; }}
  button.secondary {{ background: transparent; color: var(--text); border-color: var(--line); }}
</style></head>
<body><main><h1>{title}</h1>{body}</main></body></html>""",
        status_code=status,
        headers={"Content-Security-Policy": "frame-ancestors 'none'", "Cache-Control": "no-store"},
    )
