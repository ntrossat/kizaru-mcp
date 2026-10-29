from typing import Any

import httpx


class LightdashClient:
    """Thin async wrapper over the Lightdash REST API, called as the signed-in user."""

    def __init__(self, base_url: str, access_token: str) -> None:
        self._http = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/api/v1",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._http.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json().get("results")

    async def aclose(self) -> None:
        await self._http.aclose()
