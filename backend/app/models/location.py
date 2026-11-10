from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.db import Base, TimestampMixin
from app.models.homeassistant import HADevice, device_ref


class Area(TimestampMixin, Base):
    """Top of the location hierarchy, e.g. Back Garden, Living Room."""

    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    environment: Mapped[str] = mapped_column(String(16), default="indoor")
    description: Mapped[str | None] = mapped_column(Text)
    image_media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    spots: Mapped[list["Spot"]] = relationship(
        back_populates="area", cascade="all, delete-orphan", order_by="Spot.sort_order, Spot.name"
    )


class Spot(TimestampMixin, Base):
    """A place within an area, e.g. Windowsill, Flowerbed, Hanging Basket 1."""

    __tablename__ = "spots"
    __table_args__ = (UniqueConstraint("area_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    spot_type: Mapped[str | None] = mapped_column(String(32))
    aspect: Mapped[str | None] = mapped_column(String(8))
    sun_exposure: Mapped[str | None] = mapped_column(String(16))
    near_window: Mapped[bool | None] = mapped_column(Boolean)
    near_heat_source: Mapped[bool | None] = mapped_column(Boolean)
    near_draught: Mapped[bool | None] = mapped_column(Boolean)
    humidity_level: Mapped[str | None] = mapped_column(String(16))
    is_container: Mapped[bool | None] = mapped_column(Boolean)
    container_size: Mapped[str | None] = mapped_column(String(64))
    soil_type: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    image_media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Home Assistant device ids. Zones can water several spots; a monitor sits in exactly one.
    irrigation_zone_device_id: Mapped[str | None] = mapped_column(String(64), index=True)
    plant_monitor_device_id: Mapped[str | None] = mapped_column(String(64), unique=True)

    area: Mapped[Area] = relationship(back_populates="spots")
    irrigation_zone_device: Mapped[HADevice | None] = relationship(
        primaryjoin=lambda: foreign(Spot.irrigation_zone_device_id) == HADevice.device_id,
        viewonly=True,
        lazy="selectin",
    )
    plant_monitor_device: Mapped[HADevice | None] = relationship(
        primaryjoin=lambda: foreign(Spot.plant_monitor_device_id) == HADevice.device_id,
        viewonly=True,
        lazy="selectin",
    )
    positions: Mapped[list["Position"]] = relationship(
        back_populates="spot", cascade="all, delete-orphan", order_by="Position.sort_order, Position.id"
    )

    @property
    def irrigation_zone(self) -> dict[str, Any] | None:
        return device_ref(self.irrigation_zone_device_id, self.irrigation_zone_device, "irrigation_zone")

    @property
    def plant_monitor(self) -> dict[str, Any] | None:
        return device_ref(self.plant_monitor_device_id, self.plant_monitor_device, "plant_monitor")


class Position(TimestampMixin, Base):
    """A numbered/labelled slot within a spot, e.g. 1, 2, back-left."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("spot_id", "label"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    spot_id: Mapped[int] = mapped_column(ForeignKey("spots.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)

    spot: Mapped[Spot] = relationship(back_populates="positions")
