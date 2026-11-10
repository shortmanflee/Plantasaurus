from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.auth.deps import DB, CurrentUser
from app.db import as_utc
from app.models import Area, InstanceEvent, Media, Plant, PlantInstance, Spot
from app.schemas.common import Page
from app.schemas.media import MediaRead, MediaUpdate
from app.services import media as media_service
from app.services.crud import apply_update, ensure_exists, get_or_404, paginate

router = APIRouter(prefix="/media", tags=["media"])


def _check_links(db, plant_id, instance_id, event_id) -> None:
    ensure_exists(db, Plant, plant_id, "Plant")
    ensure_exists(db, PlantInstance, instance_id, "Instance")
    ensure_exists(db, InstanceEvent, event_id, "Event")


@router.get("", response_model=Page[MediaRead])
def list_media(
    db: DB,
    _: CurrentUser,
    plant_id: int | None = None,
    instance_id: int | None = None,
    event_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[MediaRead]:
    stmt = select(Media).order_by(Media.taken_at.desc().nulls_last(), Media.created_at.desc())
    if plant_id is not None:
        stmt = stmt.where(Media.plant_id == plant_id)
    if instance_id is not None:
        stmt = stmt.where(Media.instance_id == instance_id)
    if event_id is not None:
        stmt = stmt.where(Media.event_id == event_id)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=MediaRead, status_code=201, summary="Upload an image (multipart/form-data)")
async def upload_media(
    db: DB,
    user: CurrentUser,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    taken_at: datetime | None = Form(None),
    plant_id: int | None = Form(None),
    instance_id: int | None = Form(None),
    event_id: int | None = Form(None),
    log_photo_event: bool = Form(False, description="Also add a 'photo' event to the instance timeline"),
) -> Media:
    _check_links(db, plant_id, instance_id, event_id)
    content = await file.read(media_service.MAX_BYTES + 1)
    if log_photo_event and instance_id and not event_id:
        from app.services.placement import _when

        event = InstanceEvent(
            instance_id=instance_id,
            event_type="photo",
            occurred_at=_when(taken_at),
            user_id=user.id,
            notes=caption,
            data={},
        )
        db.add(event)
        db.flush()
        event_id = event.id
    media = media_service.save_image(
        db,
        content,
        caption=caption,
        taken_at=as_utc(taken_at) if taken_at else None,
        plant_id=plant_id,
        instance_id=instance_id,
        event_id=event_id,
        uploaded_by_id=user.id,
    )
    db.commit()
    return media


@router.get("/{media_id}", response_model=MediaRead)
def get_media(media_id: int, db: DB, _: CurrentUser) -> Media:
    return get_or_404(db, Media, media_id)


@router.get("/{media_id}/file", response_class=FileResponse, summary="Download the original image")
def media_file(media_id: int, db: DB, _: CurrentUser) -> FileResponse:
    media = get_or_404(db, Media, media_id)
    return _file(media.path, media.mime)


@router.get("/{media_id}/thumb", response_class=FileResponse, summary="Download a 400px JPEG thumbnail")
def media_thumb(media_id: int, db: DB, _: CurrentUser) -> FileResponse:
    media = get_or_404(db, Media, media_id)
    if media.thumb_path:
        return _file(media.thumb_path, "image/jpeg")
    return _file(media.path, media.mime)


def _file(rel: str, mime: str) -> FileResponse:
    path = (media_service.media_root() / rel).resolve()
    if not path.is_relative_to(media_service.media_root().resolve()) or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing")
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})


@router.patch("/{media_id}", response_model=MediaRead)
def update_media(media_id: int, payload: MediaUpdate, db: DB, _: CurrentUser) -> Media:
    media = get_or_404(db, Media, media_id)
    _check_links(db, payload.plant_id, payload.instance_id, payload.event_id)
    apply_update(media, payload)
    if media.taken_at:
        media.taken_at = as_utc(media.taken_at)
    db.commit()
    return media


@router.delete("/{media_id}", status_code=204)
def delete_media(media_id: int, db: DB, _: CurrentUser) -> None:
    media = get_or_404(db, Media, media_id)
    for model in (Plant, Area, Spot):
        for obj in db.scalars(select(model).where(model.image_media_id == media_id)):
            obj.image_media_id = None
    media_service.delete_files(media)
    db.delete(media)
    db.commit()
