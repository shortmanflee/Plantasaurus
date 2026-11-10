from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import Timestamps


class PlantFields(BaseModel):
    common_name: str = Field(min_length=1, max_length=200)
    scientific_name: str | None = None
    cultivar: str | None = None
    category: str | None = None
    description: str | None = None
    notes: str | None = None
    image_media_id: int | None = None

    min_light_lux: float | None = None
    max_light_lux: float | None = None
    min_light_mmol: float | None = None
    max_light_mmol: float | None = None
    min_temp: float | None = None
    max_temp: float | None = None
    min_env_humid: float | None = None
    max_env_humid: float | None = None
    min_soil_moist: float | None = None
    max_soil_moist: float | None = None
    min_soil_ec: float | None = None
    max_soil_ec: float | None = None

    hardiness: str | None = None
    sun_preference: str | None = None
    water_needs: str | None = None
    is_perennial: bool | None = None
    toxic_to_pets: bool | None = None

    attributes: dict[str, Any] = Field(default_factory=dict)


class PlantCreate(PlantFields):
    openplantbook_pid: str | None = None


class PlantUpdate(BaseModel):
    """All fields optional; only provided fields are changed."""

    common_name: str | None = Field(default=None, min_length=1, max_length=200)
    scientific_name: str | None = None
    cultivar: str | None = None
    category: str | None = None
    description: str | None = None
    notes: str | None = None
    image_media_id: int | None = None
    openplantbook_pid: str | None = None
    min_light_lux: float | None = None
    max_light_lux: float | None = None
    min_light_mmol: float | None = None
    max_light_mmol: float | None = None
    min_temp: float | None = None
    max_temp: float | None = None
    min_env_humid: float | None = None
    max_env_humid: float | None = None
    min_soil_moist: float | None = None
    max_soil_moist: float | None = None
    min_soil_ec: float | None = None
    max_soil_ec: float | None = None
    hardiness: str | None = None
    sun_preference: str | None = None
    water_needs: str | None = None
    is_perennial: bool | None = None
    toxic_to_pets: bool | None = None
    attributes: dict[str, Any] | None = None


class PlantRead(PlantFields, Timestamps):
    id: int
    openplantbook_pid: str | None
    opb_last_synced_at: datetime | None
    active_instance_count: int = 0
    total_instance_count: int = 0


class OPBStatus(BaseModel):
    configured: bool
    source: Literal["settings", "environment"] | None
    client_id: str | None


class OPBConfigUpdate(BaseModel):
    client_id: str | None = Field(default=None, max_length=255, description="Empty or null to remove saved credentials")
    client_secret: str | None = Field(default=None, description="Omit or null to keep the saved one.")


class OPBImportRequest(BaseModel):
    pid: str
    common_name: str | None = Field(default=None, description="Override the display name")
    download_image: bool = True


class OPBSearchResult(BaseModel):
    pid: str
    display_pid: str | None = None
    alias: str | None = None
    category: str | None = None
    already_imported_plant_id: int | None = None


class OPBPlantDetail(BaseModel):
    pid: str
    display_pid: str | None = None
    alias: str | None = None
    category: str | None = None
    image_url: str | None = None
    max_light_mmol: float | None = None
    min_light_mmol: float | None = None
    max_light_lux: float | None = None
    min_light_lux: float | None = None
    max_temp: float | None = None
    min_temp: float | None = None
    max_env_humid: float | None = None
    min_env_humid: float | None = None
    max_soil_moist: float | None = None
    min_soil_moist: float | None = None
    max_soil_ec: float | None = None
    min_soil_ec: float | None = None
