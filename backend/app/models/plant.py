from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin, UTCDateTime


class Plant(TimestampMixin, Base):
    """A 'master' plant: the species/cultivar you own one or more instances of."""

    __tablename__ = "plants"

    id: Mapped[int] = mapped_column(primary_key=True)
    common_name: Mapped[str] = mapped_column(String(200), index=True)
    scientific_name: Mapped[str | None] = mapped_column(String(200), index=True)
    cultivar: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    openplantbook_pid: Mapped[str | None] = mapped_column(String(200), unique=True)
    opb_last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    image_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media.id", ondelete="SET NULL", use_alter=True, name="fk_plant_image")
    )

    # Open Plantbook care ranges
    min_light_lux: Mapped[float | None] = mapped_column(Float)
    max_light_lux: Mapped[float | None] = mapped_column(Float)
    min_light_mmol: Mapped[float | None] = mapped_column(Float)
    max_light_mmol: Mapped[float | None] = mapped_column(Float)
    min_temp: Mapped[float | None] = mapped_column(Float)
    max_temp: Mapped[float | None] = mapped_column(Float)
    min_env_humid: Mapped[float | None] = mapped_column(Float)
    max_env_humid: Mapped[float | None] = mapped_column(Float)
    min_soil_moist: Mapped[float | None] = mapped_column(Float)
    max_soil_moist: Mapped[float | None] = mapped_column(Float)
    min_soil_ec: Mapped[float | None] = mapped_column(Float)
    max_soil_ec: Mapped[float | None] = mapped_column(Float)

    # Manually maintained traits
    hardiness: Mapped[str | None] = mapped_column(String(64))
    sun_preference: Mapped[str | None] = mapped_column(String(32))
    water_needs: Mapped[str | None] = mapped_column(String(32))
    is_perennial: Mapped[bool | None] = mapped_column(Boolean)
    toxic_to_pets: Mapped[bool | None] = mapped_column(Boolean)

    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    instances: Mapped[list["PlantInstance"]] = relationship(back_populates="plant")  # noqa: F821
