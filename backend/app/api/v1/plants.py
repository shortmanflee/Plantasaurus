from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import DB, AdminUser, CurrentUser
from app.config import get_settings
from app.db import utcnow
from app.models import Media, Plant, PlantInstance
from app.models.enums import InstanceStatus
from app.schemas.common import Page
from app.schemas.instance import InstanceRead
from app.schemas.plant import (
    OPBConfigUpdate,
    OPBImportRequest,
    OPBPlantDetail,
    OPBSearchResult,
    OPBStatus,
    PlantCreate,
    PlantRead,
    PlantUpdate,
)
from app.services import media as media_service
from app.services.crud import apply_update, commit, ensure_exists, get_or_404
from app.services.custom_fields import validate_attributes
from app.services.insights import PlantInsights, plant_insights
from app.services import openplantbook as opb
from app.services.openplantbook import get_opb_client, plant_fields_from_detail

router = APIRouter(tags=["plants"])


def _counts(db: Session, plant_ids: list[int]) -> dict[int, tuple[int, int]]:
    if not plant_ids:
        return {}
    rows = db.execute(
        select(
            PlantInstance.plant_id,
            func.count(),
            func.sum(case((PlantInstance.status == InstanceStatus.active.value, 1), else_=0)),
        )
        .where(PlantInstance.plant_id.in_(plant_ids))
        .group_by(PlantInstance.plant_id)
    ).all()
    return {pid: (int(active or 0), int(total)) for pid, total, active in rows}


def to_read(db: Session, plants: list[Plant]) -> list[PlantRead]:
    counts = _counts(db, [p.id for p in plants])
    out = []
    for p in plants:
        active, total = counts.get(p.id, (0, 0))
        out.append(
            PlantRead.model_validate(p).model_copy(update={"active_instance_count": active, "total_instance_count": total})
        )
    return out


@router.get("/plants", response_model=Page[PlantRead])
def list_plants(
    db: DB,
    _: CurrentUser,
    q: str | None = Query(None, description="Search common/scientific name"),
    category: str | None = None,
    sort: Literal["name", "-created_at", "created_at"] = "name",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[PlantRead]:
    stmt = select(Plant)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Plant.common_name.ilike(like), Plant.scientific_name.ilike(like), Plant.cultivar.ilike(like))
        )
    if category:
        stmt = stmt.where(Plant.category == category)
    order = {"name": Plant.common_name, "-created_at": Plant.created_at.desc(), "created_at": Plant.created_at}[sort]
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    plants = list(db.scalars(stmt.order_by(order).limit(limit).offset(offset)))
    return Page(items=to_read(db, plants), total=total, limit=limit, offset=offset)


@router.get("/plants/categories", response_model=list[str])
def list_categories(db: DB, _: CurrentUser) -> list[str]:
    return [c for c in db.scalars(select(Plant.category).distinct().order_by(Plant.category)) if c]


@router.post("/plants", response_model=PlantRead, status_code=201)
def create_plant(payload: PlantCreate, db: DB, _: CurrentUser) -> PlantRead:
    ensure_exists(db, Media, payload.image_media_id, "Media")
    plant = Plant(**payload.model_dump(exclude={"attributes"}))
    plant.attributes = validate_attributes(db, "plant", payload.attributes)
    db.add(plant)
    db.flush()
    _claim_media(db, plant)
    commit(db, "A plant with that Open Plantbook id already exists")
    return to_read(db, [plant])[0]


@router.get("/plants/{plant_id}", response_model=PlantRead)
def get_plant(plant_id: int, db: DB, _: CurrentUser) -> PlantRead:
    return to_read(db, [get_or_404(db, Plant, plant_id)])[0]


@router.patch("/plants/{plant_id}", response_model=PlantRead)
def update_plant(plant_id: int, payload: PlantUpdate, db: DB, _: CurrentUser) -> PlantRead:
    plant = get_or_404(db, Plant, plant_id)
    if "common_name" in payload.model_fields_set and not payload.common_name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "common_name cannot be empty")
    ensure_exists(db, Media, payload.image_media_id, "Media")
    apply_update(plant, payload, exclude={"attributes"})
    if payload.attributes is not None:
        plant.attributes = validate_attributes(db, "plant", payload.attributes, plant.attributes)
    _claim_media(db, plant)
    commit(db, "A plant with that Open Plantbook id already exists")
    return to_read(db, [plant])[0]


@router.delete("/plants/{plant_id}", status_code=204, summary="Delete a plant (only if it has no instances)")
def delete_plant(plant_id: int, db: DB, _: CurrentUser) -> None:
    plant = get_or_404(db, Plant, plant_id)
    if db.scalar(select(PlantInstance.id).where(PlantInstance.plant_id == plant_id).limit(1)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Plant has instances; delete or reassign them first"
        )
    for m in db.scalars(select(Media).where(Media.plant_id == plant_id)):
        media_service.delete_files(m)
    plant.image_media_id = None
    db.flush()
    db.delete(plant)
    db.commit()


@router.get("/plants/{plant_id}/instances", response_model=list[InstanceRead])
def plant_instances(plant_id: int, db: DB, _: CurrentUser) -> list[InstanceRead]:
    from app.api.v1.instances import list_instance_reads

    get_or_404(db, Plant, plant_id)
    return list_instance_reads(db, select(PlantInstance).where(PlantInstance.plant_id == plant_id))


@router.get("/plants/{plant_id}/insights", response_model=PlantInsights, tags=["insights"])
def get_plant_insights(plant_id: int, db: DB, _: CurrentUser) -> PlantInsights:
    return plant_insights(db, get_or_404(db, Plant, plant_id))


def _claim_media(db: Session, plant: Plant) -> None:
    if plant.image_media_id:
        m = db.get(Media, plant.image_media_id)
        if m and m.plant_id is None and m.instance_id is None:
            m.plant_id = plant.id


# ---- Open Plantbook ----------------------------------------------------------


def _opb_status(db: Session) -> OPBStatus:
    config = opb.get_config(db)
    creds = opb.resolve_credentials(config)
    return OPBStatus(
        configured=creds is not None,
        source=creds.source if creds else None,
        client_id=creds.client_id if creds else None,
    )


@router.get("/openplantbook/status", response_model=OPBStatus, tags=["open plantbook"])
def opb_status(db: DB, _: CurrentUser) -> OPBStatus:
    return _opb_status(db)


@router.put(
    "/openplantbook/config",
    response_model=OPBStatus,
    tags=["open plantbook"],
    summary="Save Open Plantbook API credentials. They are tested first and only saved if accepted.",
)
def opb_update_config(payload: OPBConfigUpdate, db: DB, _: AdminUser) -> OPBStatus:
    config = opb.get_config(db)
    client_id = (payload.client_id or "").strip() or None
    secret = payload.client_secret.strip() if payload.client_secret else None
    if client_id and not secret and client_id == config.client_id:
        secret = config.client_secret  # unchanged client id: keep the saved secret
    if client_id and not secret:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A client secret is required")
    if client_id:
        creds = opb.Credentials(client_id, secret, "settings")
        opb.OpenPlantbookClient(get_settings(), creds).check_credentials()
    config.client_id, config.client_secret = (client_id, secret) if client_id else (None, None)
    db.commit()
    return _opb_status(db)


@router.get("/openplantbook/search", response_model=list[OPBSearchResult], tags=["open plantbook"])
def opb_search(
    db: DB, _: CurrentUser, q: str = Query(min_length=2), limit: int = Query(20, ge=1, le=100)
) -> list[OPBSearchResult]:
    results = get_opb_client(db).search(q, limit)
    pids = [r.get("pid") for r in results if r.get("pid")]
    imported = dict(
        db.execute(select(Plant.openplantbook_pid, Plant.id).where(Plant.openplantbook_pid.in_(pids))).all()
    )
    return [
        OPBSearchResult(
            pid=r["pid"],
            display_pid=r.get("display_pid"),
            alias=r.get("alias"),
            category=r.get("category"),
            already_imported_plant_id=imported.get(r["pid"]),
        )
        for r in results
        if r.get("pid")
    ]


@router.get("/openplantbook/plants/{pid:path}", response_model=OPBPlantDetail, tags=["open plantbook"])
def opb_detail(pid: str, db: DB, _: CurrentUser) -> OPBPlantDetail:
    return OPBPlantDetail.model_validate(get_opb_client(db).detail(pid))


@router.post("/plants/import-opb", response_model=PlantRead, status_code=201, tags=["open plantbook"])
def import_from_opb(payload: OPBImportRequest, db: DB, _: CurrentUser) -> PlantRead:
    existing = db.scalar(select(Plant).where(Plant.openplantbook_pid == payload.pid))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already imported as plant {existing.id}")
    detail = get_opb_client(db).detail(payload.pid)
    fields = plant_fields_from_detail(detail)
    if payload.common_name:
        fields["common_name"] = payload.common_name
    plant = Plant(
        **fields,
        openplantbook_pid=detail.get("pid", payload.pid),
        opb_last_synced_at=utcnow(),
        attributes={},
    )
    db.add(plant)
    db.flush()
    if payload.download_image and detail.get("image_url"):
        media = media_service.download_image(db, detail["image_url"], plant_id=plant.id)
        if media:
            plant.image_media_id = media.id
    commit(db, "A plant with that Open Plantbook id already exists")
    return to_read(db, [plant])[0]


@router.post(
    "/plants/{plant_id}/opb-refresh",
    response_model=PlantRead,
    tags=["open plantbook"],
    summary="Re-fetch care ranges from Open Plantbook (names and notes are kept)",
)
def refresh_from_opb(plant_id: int, db: DB, _: CurrentUser, refresh_image: bool = False) -> PlantRead:
    plant = get_or_404(db, Plant, plant_id)
    if not plant.openplantbook_pid:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Plant is not linked to Open Plantbook")
    detail = get_opb_client(db).detail(plant.openplantbook_pid)
    fields = plant_fields_from_detail(detail)
    for key, value in fields.items():
        if key == "common_name":
            continue
        if key in ("scientific_name", "category") and getattr(plant, key):
            continue
        setattr(plant, key, value)
    if (refresh_image or not plant.image_media_id) and detail.get("image_url"):
        media = media_service.download_image(db, detail["image_url"], plant_id=plant.id)
        if media:
            plant.image_media_id = media.id
    plant.opb_last_synced_at = utcnow()
    db.commit()
    return to_read(db, [plant])[0]
