from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from kizaru_mcp.auth.provider import Access, LightdashOAuthProvider, SignInRequired
from kizaru_mcp.lightdash.client import LightdashClient, LightdashError

RECONNECT = "Your Lightdash sign-in has ended. Reconnect this MCP server to sign in again."
UNREACHABLE = "Couldn't reach Lightdash. Try again in a moment."

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
CREATE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)

# Arguments that go into Lightdash URL paths: a `../` or `?` in one would reach another endpoint.
Uuid = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")]
Name = Annotated[str, Field(pattern=r"^[\w-]+$")]


@asynccontextmanager
async def lightdash(provider: LightdashOAuthProvider) -> AsyncIterator[LightdashClient]:
    """A Lightdash client acting as the signed-in user, with Lightdash errors turned into tool errors."""
    token = get_access_token()
    if not isinstance(token, Access):
        raise ToolError("Not signed in.")
    try:
        access_token = await provider.lightdash_token(token.grant_id)
    except SignInRequired:
        raise ToolError(RECONNECT) from None
    except httpx.HTTPStatusError as error:
        raise ToolError(f"Lightdash error {error.response.status_code} while refreshing your sign-in. Try again later.") from None
    except httpx.HTTPError:
        raise ToolError(UNREACHABLE) from None

    async with LightdashClient(provider.settings.lightdash_base, access_token) as client:
        try:
            yield client
        except LightdashError as error:
            if error.status == 401:
                await provider.end_grant(token.grant_id)
                raise ToolError(RECONNECT) from None
            if error.status == 403:
                raise ToolError(f"Permission denied: your Lightdash role doesn't allow this. {error.message}") from None
            if error.status == 404:
                raise ToolError(f"Not found: {error.message}") from None
            raise ToolError(f"Lightdash error {error.status}: {error.message}") from None
        except httpx.HTTPError:
            raise ToolError(UNREACHABLE) from None


def pick(item: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: item.get(key) for key in keys}


def data(results: Any) -> list[dict[str, Any]]:
    """Lightdash list results, paginated (`{"data": [...]}`) or not."""
    return results["data"] if isinstance(results, dict) and "data" in results else results


def full_name(item: dict[str, Any]) -> str:
    return " ".join(part for part in (item.get("firstName"), item.get("lastName")) if part)
