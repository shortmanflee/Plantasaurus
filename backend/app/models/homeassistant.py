from datetime import datetime
from typing import Any, Literal

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, UTCDateTime

DeviceRole = Literal["irrigation_zone", "plant_monitor"]
DeviceProblem = Literal["deleted", "label_removed"]


class HAConfig(TimestampMixin, Base):
    """Single-row table (id=1) holding the Home Assistant connection saved from the UI."""

    __tablename__ = "ha_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str | None] = mapped_column(String(255))
    token: Mapped[str | None] = mapped_column(Text)
    irrigation_label: Mapped[str] = mapped_column(String(128), default="Irrigation Zone")
    monitor_label: Mapped[str] = mapped_column(String(128), default="plant")
    notify_in_ha: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    # Fingerprint of the issues last pushed to HA as a persistent notification.
    last_notified: Mapped[str | None] = mapped_column(Text)


class HADevice(TimestampMixin, Base):
    """Cached snapshot of a Home Assistant device that is labelled for us, or assigned to a spot.

    Rows for assigned devices are kept after they vanish from HA so the UI can still show
    their last-known name alongside the warning.
    """

    __tablename__ = "ha_devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    area_name: Mapped[str | None] = mapped_column(String(255))
    manufacturer: Mapped[str | None] = mapped_column(String(255))
    model: Mapped[str | None] = mapped_column(String(255))
    entities: Mapped[list[str]] = mapped_column(JSON, default=list)
    exists_in_ha: Mapped[bool] = mapped_column(Boolean, default=True)
    is_irrigation_zone: Mapped[bool] = mapped_column(Boolean, default=False)
    is_plant_monitor: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    missing_since: Mapped[datetime | None] = mapped_column(UTCDateTime())

    def has_role(self, role: DeviceRole) -> bool:
        return self.is_irrigation_zone if role == "irrigation_zone" else self.is_plant_monitor


def device_problem(device: HADevice | None, role: DeviceRole) -> DeviceProblem | None:
    if device is None or not device.exists_in_ha:
        return "deleted"
    if not device.has_role(role):
        return "label_removed"
    return None


def device_ref(device_id: str | None, device: HADevice | None, role: DeviceRole) -> dict[str, Any] | None:
    if device_id is None:
        return None
    problem = device_problem(device, role)
    return {
        "device_id": device_id,
        "name": device.name if device else None,
        "area_name": device.area_name if device else None,
        "problem": problem,
        "missing_since": device.missing_since if device and problem else None,
    }
