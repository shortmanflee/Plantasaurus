"""How MCP tools reach the Plantasaurus REST API.

Every tool goes through the real `/api/v1` endpoints, so validation, permissions and the
history rules live in one place. Two setups are supported:

* Mounted in the app (`/mcp`): requests go in-process through an ASGI transport and carry
  the API token the MCP client authenticated with.
* Standalone (stdio): requests go over HTTP to a running server with a fixed token.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token

API_PREFIX = "/api/v1"


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop unset query params and serialise values the way FastAPI expects."""
    if not params:
        return None
    out: dict[str, Any] = {}
    for key, value in params.items():
        if value is None or value == []:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif isinstance(value, (datetime, date)):
            value = value.isoformat()
        out[key] = value
    return out


def _error_message(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text or response.reason_phrase
    if isinstance(detail, list):  # FastAPI validation errors
        detail = "; ".join(
            f"{'.'.join(str(p) for p in err.get('loc', [])[1:]) or 'request'}: {err.get('msg')}" for err in detail
        )
    return f"HTTP {response.status_code}: {detail}"


class Backend:
    def __init__(self, client: httpx.AsyncClient, token: str | None = None):
        self.client = client
        self.token = token

    @classmethod
    def over_http(cls, base_url: str, token: str, timeout: float = 60) -> Backend:
        return cls(httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout), token=token)

    @classmethod
    def in_process(cls, app, token: str | None = None) -> Backend:
        transport = httpx.ASGITransport(app=app)
        return cls(httpx.AsyncClient(transport=transport, base_url="http://plantasaurus.internal", timeout=60), token)

    def _auth_headers(self) -> dict[str, str]:
        token = self.token
        if token is None:
            access = get_access_token()
            token = access.token if access else None
        if not token:
            raise ToolError("Not authenticated: send 'Authorization: Bearer pts_…' with an API token")
        return {"Authorization": f"Bearer {token}"}

    async def send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        response = await self.client.request(
            method,
            API_PREFIX + path,
            params=_clean_params(params),
            json=json,
            files=files,
            data=_clean_params(data),
            headers=self._auth_headers(),
        )
        if response.status_code >= 400:
            raise ToolError(_error_message(response))
        return response

    async def call(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self.send(method, path, **kwargs)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def get(self, path: str, **params: Any) -> Any:
        return await self.call("GET", path, params=params)

    async def post(self, path: str, body: Any = None, **params: Any) -> Any:
        return await self.call("POST", path, json=body, params=params)

    async def patch(self, path: str, body: Any) -> Any:
        return await self.call("PATCH", path, json=body)

    async def delete(self, path: str, **params: Any) -> None:
        await self.call("DELETE", path, params=params)
