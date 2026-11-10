import io
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Media

MAX_BYTES = 20 * 1024 * 1024
THUMB_SIZE = (400, 400)
_FORMATS = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp"), "GIF": ("image/gif", "gif")}


def media_root() -> Path:
    root = get_settings().media_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_image(
    db: Session,
    content: bytes,
    *,
    source_url: str | None = None,
    caption: str | None = None,
    taken_at: datetime | None = None,
    plant_id: int | None = None,
    instance_id: int | None = None,
    event_id: int | None = None,
    uploaded_by_id: int | None = None,
) -> Media:
    if len(content) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image too large (max 20MB)")
    try:
        img = Image.open(io.BytesIO(content))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "File is not a supported image") from exc

    fmt = img.format or "JPEG"
    if fmt not in _FORMATS:  # normalise HEIC/BMP/TIFF etc. to JPEG
        buf = io.BytesIO()
        ImageOps.exif_transpose(img).convert("RGB").save(buf, "JPEG", quality=90)
        content, fmt = buf.getvalue(), "JPEG"
    mime, ext = _FORMATS[fmt]

    now = datetime.now()
    rel_dir = Path(f"{now:%Y}/{now:%m}")
    (media_root() / rel_dir).mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex
    rel_path = rel_dir / f"{stem}.{ext}"
    (media_root() / rel_path).write_bytes(content)

    thumb_rel = rel_dir / f"{stem}_thumb.jpg"
    thumb = ImageOps.exif_transpose(img)
    thumb.thumbnail(THUMB_SIZE)
    thumb.convert("RGB").save(media_root() / thumb_rel, "JPEG", quality=80)

    media = Media(
        path=str(rel_path),
        thumb_path=str(thumb_rel),
        mime=mime,
        width=img.width,
        height=img.height,
        source_url=source_url,
        caption=caption,
        taken_at=taken_at,
        plant_id=plant_id,
        instance_id=instance_id,
        event_id=event_id,
        uploaded_by_id=uploaded_by_id,
    )
    db.add(media)
    db.flush()
    return media


def download_image(db: Session, url: str, **kwargs) -> Media | None:
    """Download an image from a URL into the media store. Returns None on failure."""
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            if len(resp.content) > MAX_BYTES:
                return None
            return save_image(db, resp.content, source_url=url, **kwargs)
    except (httpx.HTTPError, HTTPException):
        return None


def delete_files(media: Media) -> None:
    for rel in (media.path, media.thumb_path):
        if rel:
            (media_root() / rel).unlink(missing_ok=True)
