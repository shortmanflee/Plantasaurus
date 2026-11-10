from sqlalchemy import JSON, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class CustomFieldDefinition(TimestampMixin, Base):
    __tablename__ = "custom_field_definitions"
    __table_args__ = (UniqueConstraint("entity", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(16), index=True)
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(16))
    options: Mapped[list[str] | None] = mapped_column(JSON)
    help_text: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
