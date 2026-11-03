import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from mcp.server.mcpserver.exceptions import ToolError

from kizaru_mcp.config import Settings
from kizaru_mcp.lightdash import LightdashClient, LightdashError
from kizaru_mcp.server import create_server


def test_create_server():
    settings = Settings(
        _env_file=None, lightdash_client_id="id", lightdash_client_secret="secret", fernet_key=Fernet.generate_key().decode()
    )
    assert create_server(settings).name == "kizaru-mcp"


async def test_tool_arguments_cannot_reach_other_endpoints():
    settings = Settings(
        _env_file=None, lightdash_client_id="id", lightdash_client_secret="secret", fernet_key=Fernet.generate_key().decode()
    )
    server = create_server(settings)
    project = "3675b69e-8324-4110-bdca-059031aa8da3"
    for name, arguments in [
        ("update_project_access", {"project_uuid": project, "user_uuid": "../../../org/users/x", "role": "admin"}),
        ("list_spaces", {"project_uuid": "x?evil=1"}),
        ("get_explore", {"project_uuid": project, "explore": "../orders"}),
    ]:
        with pytest.raises(ToolError, match="validation error"):
            await server.call_tool(name, arguments)


def test_missing_settings_stop_the_server():
    with pytest.raises(SystemExit, match="LIGHTDASH_CLIENT_ID, LIGHTDASH_CLIENT_SECRET, FERNET_KEY"):
        Settings(_env_file=None).check()


@respx.mock
async def test_client_sends_bearer_and_unwraps_results():
    route = respx.get("http://lightdash.test/api/v1/user").mock(
        return_value=httpx.Response(200, json={"status": "ok", "results": {"email": "demo@lightdash.com"}})
    )
    async with LightdashClient("http://lightdash.test", "token") as client:
        assert await client.request("GET", "/api/v1/user") == {"email": "demo@lightdash.com"}
    assert route.calls[0].request.headers["Authorization"] == "Bearer token"


@respx.mock
async def test_client_handles_empty_bodies_and_errors():
    respx.put("http://lightdash.test/api/v1/groups/g/members/u").mock(return_value=httpx.Response(204))
    respx.get("http://lightdash.test/api/v2/orgs/o/roles").mock(
        return_value=httpx.Response(
            403, json={"status": "error", "error": {"statusCode": 403, "name": "ForbiddenError", "message": "Not allowed"}}
        )
    )
    async with LightdashClient("http://lightdash.test", "token") as client:
        assert await client.request("PUT", "/api/v1/groups/g/members/u") is None
        with pytest.raises(LightdashError) as error:
            await client.get("/api/v2/orgs/o/roles")
    assert (error.value.status, error.value.message) == (403, "Not allowed")


@respx.mock
async def test_client_treats_redirects_as_errors():
    respx.delete("http://lightdash.test/api/v1/schedulers/s").mock(
        return_value=httpx.Response(302, headers={"Location": "/login"})
    )
    async with LightdashClient("http://lightdash.test", "token") as client:
        with pytest.raises(LightdashError) as error:
            await client.request("DELETE", "/api/v1/schedulers/s")
    assert error.value.status == 302
