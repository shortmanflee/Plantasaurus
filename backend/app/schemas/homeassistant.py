from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.homeassistant import DeviceProblem, DeviceRole
from app.schemas.common import ORMModel, ResponseModel

DEVICE_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"


class HADeviceRef(ResponseModel):
    """An HA device as assigned to a spot. `problem` is set when it needs attention."""

    device_id: str
    name: str | None
    area_name: str | None
    problem: DeviceProblem | None = Field(
        description="deleted: the device no longer exists in HA. label_removed: it exists but lost its label."
    )
    missing_since: datetime | None


class HADeviceRead(ORMModel):
    device_id: str
    name: str | None
    area_name: str | None
    manufacturer: str | None
    model: str | None
    entities: list[str]
    last_seen_at: datetime | None
    assigned_spot_ids: list[int] = Field(default_factory=list)


class HAStatus(ResponseModel):
    configured: bool
    source: Literal["settings", "environment", "supervisor"] | None
    url: str | None
    token_set: bool
    irrigation_label: str
    monitor_label: str
    notify_in_ha: bool
    sync_interval_seconds: int
    last_sync_at: datetime | None
    last_sync_error: str | None
    issue_count: int


class HAConfigUpdate(BaseModel):
    url: str | None = Field(default=None, max_length=255, description="e.g. http://homeassistant.local:8123")
    token: str | None = Field(
        default=None, description="Long-lived access token of an admin user. Omit or null to keep the saved one."
    )
    irrigation_label: str = Field(default="Irrigation Zone", min_length=1, max_length=128)
    monitor_label: str = Field(default="plant", min_length=1, max_length=128)
    notify_in_ha: bool = True


class HAIssue(ResponseModel):
    spot_id: int
    spot_name: str
    area_id: int
    area_name: str
    role: DeviceRole
    device_id: str
    device_name: str | None
    problem: DeviceProblem
    missing_since: datetime | None
