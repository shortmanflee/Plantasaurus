from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin, UTCDateTime
from app.models.location import Position, Spot
from app.models.plant import Plant


class PlantInstance(TimestampMixin, Base):
    """A physical plant (or group of identical plants) you own."""

    __tablename__ = "plant_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", ondelete="RESTRICT"), index=True)
    nickname: Mapped[str | None] = mapped_column(String(128))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)

    current_spot_id: Mapped[int | None] = mapped_column(
        ForeignKey("spots.id", ondelete="SET NULL"), index=True
    )
    current_position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id", ondelete="SET NULL"))

    acquired_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(16))
    source_detail: Mapped[str | None] = mapped_column(String(255))
    cost: Mapped[float | None] = mapped_column(Float)
    parent_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("plant_instances.id", ondelete="SET NULL")
    )

    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    end_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    plant: Mapped[Plant] = relationship(back_populates="instances")
    current_spot: Mapped[Spot | None] = relationship(foreign_keys=[current_spot_id])
    current_position: Mapped[Position | None] = relationship(foreign_keys=[current_position_id])
    placements: Mapped[list["Placement"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan", order_by="Placement.started_at"
    )


class Placement(Base):
    """A period of time an instance spent in a spot/position."""

    __tablename__ = "placements"

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("plant_instances.id", ondelete="CASCADE"), index=True
    )
    spot_id: Mapped[int | None] = mapped_column(ForeignKey("spots.id", ondelete="SET NULL"), index=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    start_event_id: Mapped[int | None] = mapped_column(ForeignKey("instance_events.id", ondelete="SET NULL"))
    end_event_id: Mapped[int | None] = mapped_column(ForeignKey("instance_events.id", ondelete="SET NULL"))

    instance: Mapped[PlantInstance] = relationship(back_populates="placements")
    spot: Mapped[Spot | None] = relationship()
    position: Mapped[Position | None] = relationship()


class InstanceEvent(TimestampMixin, Base):
    """Append-only timeline entry for an instance."""

    __tablename__ = "instance_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("plant_instances.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    from_spot_id: Mapped[int | None] = mapped_column(ForeignKey("spots.id", ondelete="SET NULL"))
    from_position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id", ondelete="SET NULL"))
    to_spot_id: Mapped[int | None] = mapped_column(ForeignKey("spots.id", ondelete="SET NULL"))
    to_position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id", ondelete="SET NULL"))


class Assessment(TimestampMixin, Base):
    """How well an instance is doing, optionally tied to the placement at the time."""

    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("plant_instances.id", ondelete="CASCADE"), index=True
    )
    placement_id: Mapped[int | None] = mapped_column(ForeignKey("placements.id", ondelete="SET NULL"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("instance_events.id", ondelete="SET NULL"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    assessed_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    health: Mapped[int | None] = mapped_column(Integer)
    vigour: Mapped[int | None] = mapped_column(Integer)
    flowering_fruiting: Mapped[int | None] = mapped_column(Integer)
    overall: Mapped[int | None] = mapped_column(Integer)
    would_buy_again: Mapped[str | None] = mapped_column(String(8))
    would_keep_location: Mapped[str | None] = mapped_column(String(16))
    is_final: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text)
