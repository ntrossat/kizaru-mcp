from mcp.server.mcpserver import MCPServer

from lightdash_mcp.config import Settings


def create_server() -> MCPServer:
    # Auth (AuthSettings + LightdashOAuthProvider) is wired in Phase 1, once Phase 0 confirms the OAuth path.
    return MCPServer(
        name="lightdash-mcp",
        instructions="Admin, governance and content-lifecycle tools for Lightdash.",
    )


def main() -> None:
    settings = Settings()
    create_server().run("streamable-http", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
