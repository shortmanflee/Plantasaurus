from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import Aspect, Environment, Level, SunExposure
from app.schemas.common import Timestamps
from app.schemas.homeassistant import DEVICE_ID_PATTERN, HADeviceRef


class AreaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    environment: Environment = Environment.indoor
    description: str | None = None
    image_media_id: int | None = None
    sort_order: int = 0
    attributes: dict[str, Any] = Field(default_factory=dict)


class AreaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    environment: Environment | None = None
    description: str | None = None
    image_media_id: int | None = None
    sort_order: int | None = None
    attributes: dict[str, Any] | None = None


class AreaRead(AreaCreate, Timestamps):
    id: int


class SpotTraits(BaseModel):
    spot_type: str | None = Field(
        default=None,
        description="e.g. windowsill, shelf, flowerbed, raised_bed, border, pot, hanging_basket, lawn",
    )
    aspect: Aspect | None = None
    sun_exposure: SunExposure | None = None
    near_window: bool | None = None
    near_heat_source: bool | None = None
    near_draught: bool | None = None
    humidity_level: Level | None = None
    is_container: bool | None = None
    container_size: str | None = None
    soil_type: str | None = None


class SpotDevices(BaseModel):
    irrigation_zone_device_id: str | None = Field(
        default=None, pattern=DEVICE_ID_PATTERN, description="Home Assistant device labelled as an irrigation zone"
    )
    plant_monitor_device_id: str | None = Field(
        default=None, pattern=DEVICE_ID_PATTERN, description="Home Assistant device labelled as a plant monitor"
    )


class SpotCreate(SpotTraits, SpotDevices):
    area_id: int
    name: str = Field(min_length=1, max_length=128)
    notes: str | None = None
    image_media_id: int | None = None
    sort_order: int = 0
    archived: bool = False
    attributes: dict[str, Any] = Field(default_factory=dict)
    position_count: int = Field(default=0, ge=0, le=200, description="Auto-create positions 1..N")


class SpotUpdate(SpotDevices):
    area_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    spot_type: str | None = None
    aspect: Aspect | None = None
    sun_exposure: SunExposure | None = None
    near_window: bool | None = None
    near_heat_source: bool | None = None
    near_draught: bool | None = None
    humidity_level: Level | None = None
    is_container: bool | None = None
    container_size: str | None = None
    soil_type: str | None = None
    notes: str | None = None
    image_media_id: int | None = None
    sort_order: int | None = None
    archived: bool | None = None
    attributes: dict[str, Any] | None = None


class SpotRead(SpotTraits, Timestamps):
    id: int
    area_id: int
    name: str
    notes: str | None
    image_media_id: int | None
    sort_order: int
    archived: bool
    attributes: dict[str, Any]
    irrigation_zone_device_id: str | None
    plant_monitor_device_id: str | None
    irrigation_zone: HADeviceRef | None
    plant_monitor: HADeviceRef | None


class PositionCreate(BaseModel):
    spot_id: int
    label: str = Field(min_length=1, max_length=32)
    sort_order: int | None = Field(default=None, description="Defaults to after the last position")
    notes: str | None = None


class PositionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=32)
    sort_order: int | None = None
    notes: str | None = None


class PositionRead(Timestamps):
    id: int
    spot_id: int
    label: str
    sort_order: int
    notes: str | None


class OccupantSummary(BaseModel):
    instance_id: int
    plant_id: int
    plant_name: str
    nickname: str | None
    position_id: int | None


class PositionNode(BaseModel):
    id: int
    label: str
    occupants: list[OccupantSummary]


class SpotNode(SpotRead):
    positions: list[PositionNode]
    unpositioned_occupants: list[OccupantSummary]


class AreaNode(AreaRead):
    spots: list[SpotNode]
