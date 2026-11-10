"""Client for the Open Plantbook API (https://open.plantbook.io).

Credentials (client id/secret) stay server-side; the frontend only talks to our proxy.
They come from the UI settings (opb_config table) or, failing that, PLANTASAURUS_OPB_CLIENT_ID/SECRET.
"""

import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import OPBConfig

CARE_FIELDS = (
    "min_light_lux",
    "max_light_lux",
    "min_light_mmol",
    "max_light_mmol",
    "min_temp",
    "max_temp",
    "min_env_humid",
    "max_env_humid",
    "min_soil_moist",
    "max_soil_moist",
    "min_soil_ec",
    "max_soil_ec",
)

SEARCH_TTL = 300


@dataclass(frozen=True)
class Credentials:
    client_id: str
    client_secret: str
    source: Literal["settings", "environment"]


def get_config(db: Session) -> OPBConfig:
    config = db.get(OPBConfig, 1)
    if config is None:
        config = OPBConfig(id=1)
        db.add(config)
        db.flush()
    return config


def resolve_credentials(config: OPBConfig | None, settings: Settings | None = None) -> Credentials | None:
    """UI settings win, then PLANTASAURUS_OPB_CLIENT_ID/SECRET."""
    if config is not None and config.client_id and config.client_secret:
        return Credentials(config.client_id, config.client_secret, "settings")
    settings = settings or get_settings()
    if settings.opb_client_id and settings.opb_client_secret:
        return Credentials(settings.opb_client_id, settings.opb_client_secret, "environment")
    return None


class OpenPlantbookClient:
    def __init__(
        self,
        settings: Settings,
        credentials: Credentials | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.settings = settings
        self.credentials = credentials
        self._transport = transport
        self._token: str | None = None
        self._token_expires: float = 0
        self._search_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    @property
    def configured(self) -> bool:
        return self.credentials is not None

    def use(self, credentials: Credentials | None) -> "OpenPlantbookClient":
        """Switch credentials, dropping the cached token if they changed."""
        if credentials != self.credentials:
            self.credentials = credentials
            self._token = None
            self._token_expires = 0
        return self

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.settings.opb_base_url, timeout=15, transport=self._transport)

    def check_credentials(self) -> None:
        """Fetch a fresh token, raising HTTPException(502) if Open Plantbook refuses or can't be reached."""
        self._token = None
        try:
            with self._client() as client:
                self._get_token(client)
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not reach Open Plantbook: {exc}") from exc

    def _get_token(self, client: httpx.Client) -> str:
        if self._token and time.monotonic() < self._token_expires - 60:
            return self._token
        resp = client.post(
            "/token/",
            data={
                "grant_type": "client_credentials",
                "client_id": self.credentials.client_id,
                "client_secret": self.credentials.client_secret,
            },
        )
        if resp.status_code in (400, 401):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Open Plantbook rejected the client credentials")
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._token_expires = time.monotonic() + float(body.get("expires_in", 3600))
        return self._token

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.configured:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Open Plantbook is not configured. Add API credentials under Settings → Integrations.",
            )
        try:
            with self._client() as client:
                token = self._get_token(client)
                resp = client.get(path, params=params, headers={"Authorization": f"Bearer {token}"})
                if resp.status_code == 401:  # token expired early; retry once
                    self._token = None
                    token = self._get_token(client)
                    resp = client.get(path, params=params, headers={"Authorization": f"Bearer {token}"})
                if resp.status_code == 404:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "Plant not found in Open Plantbook")
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Open Plantbook request failed: {exc}") from exc

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        key = f"{query.strip().lower()}|{limit}"
        cached = self._search_cache.get(key)
        if cached and time.monotonic() - cached[0] < SEARCH_TTL:
            return cached[1]
        body = self._get("/plant/search", params={"alias": query.strip(), "limit": limit})
        results = body.get("results", []) if isinstance(body, dict) else []
        self._search_cache[key] = (time.monotonic(), results)
        return results

    def detail(self, pid: str) -> dict[str, Any]:
        return self._get(f"/plant/detail/{quote(pid, safe='')}/")


_client: OpenPlantbookClient | None = None


def get_opb_client(db: Session) -> OpenPlantbookClient:
    """The shared client (keeps its token and search cache), using the currently configured credentials."""
    global _client
    settings = get_settings()
    if _client is None:
        _client = OpenPlantbookClient(settings)
    return _client.use(resolve_credentials(db.get(OPBConfig, 1), settings))


def plant_fields_from_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """Map an Open Plantbook detail payload onto Plant model fields."""
    fields: dict[str, Any] = {k: _num(detail.get(k)) for k in CARE_FIELDS}
    display = detail.get("display_pid") or detail.get("pid")
    fields["scientific_name"] = display
    fields["category"] = detail.get("category") or None
    alias = (detail.get("alias") or "").strip()
    fields["common_name"] = alias.title() if alias and alias.lower() != (display or "").lower() else display
    return fields


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None
