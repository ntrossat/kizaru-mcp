import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

import uvicorn
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.requests import Request
from starlette.responses import JSONResponse

from kizaru_mcp.auth.provider import SCOPE, LightdashOAuthProvider
from kizaru_mcp.auth.store import Store
from kizaru_mcp.config import Settings
from kizaru_mcp.tools import access, content, data, schedulers

SHUTDOWN_TIMEOUT = 3

logger = logging.getLogger("kizaru_mcp.audit")


async def audit(ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
    """Log every tool call: who, which tool, with which arguments, and whether it failed."""
    if ctx.method != "tools/call" or not ctx.params:
        return await call_next(ctx)
    failed = True  # unless the call returns a result without an error
    try:
        result = await call_next(ctx)
        # The result comes as the wire dict, or as a model if a handler returns one.
        failed = bool(result.get("isError") if isinstance(result, dict) else getattr(result, "is_error", False))
        return result
    finally:
        token = get_access_token()
        logger.info(
            "user=%s tool=%s arguments=%s error=%s",
            token.subject if token else None,
            ctx.params.get("name"),
            json.dumps(ctx.params.get("arguments") or {}, default=str),
            failed,
        )


def create_server(settings: Settings, redis: Redis | None = None) -> MCPServer:
    store = Store(redis or Redis.from_url(settings.redis_url), settings.fernet_key)
    provider = LightdashOAuthProvider(settings, store)

    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[None]:
        yield
        await provider.http.aclose()

    server = MCPServer(
        name="kizaru-mcp",
        instructions="Query Lightdash data, and administer it: access, content and deliveries. "
        "Every call runs as the signed-in Lightdash user, with their permissions.",
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=settings.public_url,
            resource_server_url=f"{settings.public_url}/mcp",
            # Tokens are only issued by this server, for this server.
            validate_token_resource=False,
            client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]),
            revocation_options=RevocationOptions(enabled=True),
        ),
        lifespan=lifespan,
        middleware=[audit],
    )

    async def health(_: Request) -> JSONResponse:
        """Up when Redis answers. Lightdash being down doesn't make this server unhealthy."""
        try:
            await store.ping()
        except RedisError:
            return JSONResponse({"status": "Redis unreachable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    server.custom_route("/health", methods=["GET"])(health)
    server.custom_route("/oauth/consent", methods=["GET"])(provider.consent_page)
    server.custom_route("/oauth/consent", methods=["POST"])(provider.consent_submit)
    server.custom_route("/oauth/lightdash/callback", methods=["GET"])(provider.lightdash_callback)
    for tools in (access, content, schedulers, data):
        tools.register(server, provider)
    return server


def transport_security(settings: Settings) -> TransportSecuritySettings:
    """The SDK's localhost defaults, plus PUBLIC_URL's host so requests through a tunnel are accepted."""
    public = urlparse(settings.public_url)
    return TransportSecuritySettings(
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", public.netloc],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*", f"{public.scheme}://{public.netloc}"],
    )


def main() -> None:
    settings = Settings()
    settings.check()
    app = create_server(settings).streamable_http_app(transport_security=transport_security(settings), host=settings.host)
    # Ctrl+C is a normal stop: no traceback. MCP clients keep a stream open, so a stop waits for them
    # at most SHUTDOWN_TIMEOUT seconds instead of until they disconnect.
    try:
        uvicorn.run(app, host=settings.host, port=settings.port, timeout_graceful_shutdown=SHUTDOWN_TIMEOUT)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
