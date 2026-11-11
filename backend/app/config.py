from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLANTASAURUS_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    secret_key: str = ""
    database_url: str | None = None
    static_dir: Path | None = None  # built SPA; defaults to ../frontend/dist if present

    opb_client_id: str | None = None
    opb_client_secret: str | None = None
    opb_base_url: str = "https://open.plantbook.io/api/v1"

    session_max_age_days: int = 30
    cookie_secure: bool = False

    # Home Assistant ingress: trust X-Remote-User-* headers from the supervisor.
    ingress_mode: bool = False
    ingress_trusted_ips: list[str] = ["172.30.32.2"]

    # Home Assistant connection. Settings saved in the UI take precedence over these.
    ha_url: str | None = None
    ha_token: str | None = None
    # How often to re-check that assigned irrigation zones / plant monitors still exist. 0 disables.
    ha_sync_interval_seconds: int = 900

    # MCP server at /mcp (streamable HTTP, authenticated with API tokens). Admins can switch it
    # on and off in the UI; false here removes the endpoint entirely and locks the switch.
    mcp_enabled: bool = True

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'plantasaurus.db').resolve()}"

    @property
    def opb_configured(self) -> bool:
        return bool(self.opb_client_id and self.opb_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def resolve_secret_key(settings: Settings) -> str:
    """Use the configured secret, or persist a generated one in the data dir."""
    if settings.secret_key:
        return settings.secret_key
    import secrets

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = settings.data_dir / ".secret_key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()
