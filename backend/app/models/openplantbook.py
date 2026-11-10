from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class OPBConfig(TimestampMixin, Base):
    """Single-row table (id=1) holding Open Plantbook API credentials saved from the UI."""

    __tablename__ = "opb_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str | None] = mapped_column(String(255))
    client_secret: Mapped[str | None] = mapped_column(Text)
