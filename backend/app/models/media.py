from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, UTCDateTime


class Media(TimestampMixin, Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(255))  # relative to media dir
    thumb_path: Mapped[str | None] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    taken_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id", ondelete="CASCADE"), index=True)
    instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("plant_instances.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[int | None] = mapped_column(ForeignKey("instance_events.id", ondelete="SET NULL"))
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
