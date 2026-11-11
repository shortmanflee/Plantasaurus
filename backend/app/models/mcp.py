from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class MCPConfig(TimestampMixin, Base):
    """Single-row table (id=1) holding the MCP server switch set from the UI."""

    __tablename__ = "mcp_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
