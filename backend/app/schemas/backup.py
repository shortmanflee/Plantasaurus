from datetime import datetime

from pydantic import Field

from app.models.backup import BackupStatus
from app.schemas.common import ORMModel, ResponseModel


class BackupRead(ORMModel):
    id: int
    status: BackupStatus
    filename: str | None
    size_bytes: int | None
    counts: dict[str, int] = Field(
        description="Rows per table (plants, plant_instances, instance_events, media, ...) and media_files"
    )
    error: str | None
    note: str | None
    created_by_id: int | None
    created_at: datetime
    completed_at: datetime | None


class RestoreResult(ResponseModel):
    counts: dict[str, int] = Field(description="Rows restored per table, and media_files")
    safety_backup_id: int = Field(description="Backup of the data as it was just before the restore")
