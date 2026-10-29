import httpx
import respx

from lightdash_mcp.lightdash.client import LightdashClient
from lightdash_mcp.server import create_server


def test_create_server():
    assert create_server().name == "lightdash-mcp"


@respx.mock
async def test_client_sends_bearer_and_unwraps_results():
    route = respx.get("http://lightdash.test/api/v1/user").mock(
        return_value=httpx.Response(200, json={"status": "ok", "results": {"email": "demo@lightdash.com"}})
    )
    client = LightdashClient("http://lightdash.test", "token")
    assert await client.request("GET", "/user") == {"email": "demo@lightdash.com"}
    assert route.calls[0].request.headers["Authorization"] == "Bearer token"
    await client.aclose()
