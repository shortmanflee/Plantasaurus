from datetime import datetime

from pydantic import BaseModel, computed_field

from app.schemas.common import Timestamps


class MediaRead(Timestamps):
    id: int
    mime: str
    width: int | None
    height: int | None
    source_url: str | None
    caption: str | None
    taken_at: datetime | None
    plant_id: int | None
    instance_id: int | None
    event_id: int | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        return f"api/v1/media/{self.id}/file"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def thumb_url(self) -> str:
        return f"api/v1/media/{self.id}/thumb"


class MediaUpdate(BaseModel):
    caption: str | None = None
    taken_at: datetime | None = None
    plant_id: int | None = None
    instance_id: int | None = None
    event_id: int | None = None
