from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import new_session
from app.models import MCPConfig


def get_config(db: Session) -> MCPConfig:
    config = db.get(MCPConfig, 1)
    if config is None:
        config = MCPConfig(id=1, enabled=True)
        db.add(config)
        db.flush()
    return config


def is_available() -> bool:
    """False when PLANTASAURUS_MCP_ENABLED=false: the endpoint isn't mounted and the UI can't turn it on."""
    return get_settings().mcp_enabled


def is_enabled(db: Session) -> bool:
    if not is_available():
        return False
    config = db.get(MCPConfig, 1)
    return True if config is None else config.enabled


def is_enabled_now() -> bool:
    with new_session() as db:
        return is_enabled(db)
