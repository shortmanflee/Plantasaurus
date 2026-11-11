from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.auth.deps import DB, AdminUser
from app.models import Backup
from app.schemas.backup import BackupRead, RestoreResult
from app.services import backup as backup_service
from app.services.backup import BackupError
from app.services.crud import get_or_404

router = APIRouter(prefix="/backups", tags=["backups"])

UPLOAD_CHUNK = 1024 * 1024


def _conflict(exc: BackupError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("", response_model=list[BackupRead])
def list_backups(db: DB, _: AdminUser) -> list[Backup]:
    return list(db.scalars(select(Backup).order_by(Backup.created_at.desc(), Backup.id.desc())))


@router.post(
    "",
    response_model=BackupRead,
    status_code=202,
    summary="Start a backup",
    description=(
        "Builds a zip with every plant, instance, location, placement, event, assessment, custom field "
        "and photo. Users, API tokens and integration credentials are not included.\n\n"
        "By default the job runs in the background (202): poll `GET /backups/{id}` until `status` is "
        "`ready` or `failed`. With `wait=true` the request returns once the backup is finished (201), "
        "which is simpler for scripts and MCP clients."
    ),
    responses={201: {"model": BackupRead, "description": "Finished backup (with `wait=true`)"}},
)
def create_backup(
    db: DB,
    user: AdminUser,
    background: BackgroundTasks,
    response: Response,
    wait: bool = Query(False, description="Build the backup before responding instead of in the background"),
) -> Backup:
    try:
        backup = backup_service.start_backup(db, user)
    except BackupError as exc:
        raise _conflict(exc) from exc
    if not wait:
        background.add_task(backup_service.run_backup, backup.id)
        return backup
    backup_service.run_backup(backup.id)
    db.refresh(backup)
    response.status_code = status.HTTP_201_CREATED
    return backup


@router.get("/{backup_id}", response_model=BackupRead)
def get_backup(backup_id: int, db: DB, _: AdminUser) -> Backup:
    return get_or_404(db, Backup, backup_id)


@router.get("/{backup_id}/download", response_class=FileResponse, summary="Download the backup zip")
def download_backup(backup_id: int, db: DB, _: AdminUser) -> FileResponse:
    backup = get_or_404(db, Backup, backup_id)
    path = backup_service.backup_path(backup)
    if backup.status != "ready" or path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup file is not available")
    return FileResponse(path, media_type="application/zip", filename=backup.filename)


@router.delete("/{backup_id}", status_code=204)
def delete_backup(backup_id: int, db: DB, _: AdminUser) -> None:
    try:
        backup_service.delete_backup(db, get_or_404(db, Backup, backup_id))
    except BackupError as exc:
        raise _conflict(exc) from exc


def _restore(db, user, path) -> RestoreResult:
    try:
        counts, safety_id = backup_service.restore_with_safety_backup(db, user, path)
    except BackupError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return RestoreResult(counts=counts, safety_backup_id=safety_id)


_RESTORE_DESCRIPTION = (
    "Replaces **all** plant data and photos with the backup's contents. The current data is backed up "
    "first (listed with the note 'Automatic, before restore'); restore that backup to undo. Users, API "
    "tokens and integration settings are left as they are; people referenced in the backup are matched "
    "to existing users by username."
)


@router.post(
    "/{backup_id}/restore",
    response_model=RestoreResult,
    summary="Restore from a backup on this server",
    description=_RESTORE_DESCRIPTION + " No upload needed, so this is the one to use from MCP clients.",
)
def restore_backup(backup_id: int, db: DB, user: AdminUser) -> RestoreResult:
    backup = get_or_404(db, Backup, backup_id)
    path = backup_service.backup_path(backup)
    if backup.status != "ready" or path is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Backup file is not available")
    return _restore(db, user, path)


@router.post(
    "/restore",
    response_model=RestoreResult,
    summary="Restore from an uploaded backup zip (multipart/form-data)",
    description=_RESTORE_DESCRIPTION,
)
async def restore_upload(db: DB, user: AdminUser, file: UploadFile = File(...)) -> RestoreResult:
    path = backup_service.upload_path()
    try:
        with path.open("wb") as out:
            while chunk := await file.read(UPLOAD_CHUNK):
                out.write(chunk)
        return await run_in_threadpool(_restore, db, user, path)
    finally:
        path.unlink(missing_ok=True)
