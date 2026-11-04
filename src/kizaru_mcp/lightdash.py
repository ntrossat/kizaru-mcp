from typing import Any, Self

import httpx


class LightdashError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300] or response.reason_phrase
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return error.get("message") or error.get("name") or response.reason_phrase
    return str(error or body)[:300]


class LightdashClient:
    """Thin async wrapper over the Lightdash REST API, called as the signed-in user.

    Paths are absolute from the site root (`/api/v1/...`, `/api/v2/...`).
    """

    def __init__(self, base_url: str, access_token: str) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, headers={"Authorization": f"Bearer {access_token}"}, timeout=60)

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._http.request(method, path, **kwargs)
        if not response.is_success:
            raise LightdashError(response.status_code, _error_message(response))
        if not response.content:
            return None
        body = response.json()
        return body.get("results") if isinstance(body, dict) and "results" in body else body

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params={k: v for k, v in params.items() if v is not None})

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
