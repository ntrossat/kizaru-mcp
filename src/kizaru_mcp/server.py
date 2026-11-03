from urllib.parse import urlparse

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from redis.asyncio import Redis

from kizaru_mcp.auth.provider import SCOPE, LightdashOAuthProvider
from kizaru_mcp.auth.store import Store
from kizaru_mcp.config import Settings
from kizaru_mcp.tools import access, content, data, schedulers


def create_server(settings: Settings, redis: Redis | None = None) -> MCPServer:
    store = Store(redis or Redis.from_url(settings.redis_url), settings.fernet_key)
    provider = LightdashOAuthProvider(settings, store)
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
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]
            ),
            revocation_options=RevocationOptions(enabled=True),
        ),
    )
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
    # Ctrl+C is a normal stop: no traceback.
    try:
        create_server(settings).run(
            "streamable-http", host=settings.host, port=settings.port, transport_security=transport_security(settings)
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
