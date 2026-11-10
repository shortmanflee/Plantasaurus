from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth.deps import DB, CurrentUser
from app.models import Assessment, InstanceEvent, Media, Placement, Plant, PlantInstance, Spot
from app.models.enums import EventType, InstanceStatus
from app.schemas.common import Page
from app.schemas.instance import (
    AssessRequest,
    AssessmentRead,
    EventRead,
    InstanceCreate,
    InstanceDetail,
    InstanceRead,
    InstanceUpdate,
    MoveRequest,
    PlacementRead,
    PropagateRequest,
    RepotRequest,
    RetireRequest,
    ReviveRequest,
    TimelineEntry,
    TransplantRequest,
)
from app.schemas.media import MediaRead
from app.services import media as media_service
from app.services import placement as svc
from app.services.crud import get_or_404
from app.services.custom_fields import validate_attributes

router = APIRouter(prefix="/instances", tags=["instances"])

_LOAD = (
    selectinload(PlantInstance.plant),
    selectinload(PlantInstance.current_spot).selectinload(Spot.area),
    selectinload(PlantInstance.current_position),
)


def _latest_ratings(db: Session, ids: list[int]) -> dict[int, int | None]:
    if not ids:
        return {}
    latest = (
        select(Assessment.instance_id, func.max(Assessment.assessed_at).label("at"))
        .where(Assessment.instance_id.in_(ids), Assessment.overall.is_not(None))
        .group_by(Assessment.instance_id)
        .subquery()
    )
    rows = db.execute(
        select(Assessment.instance_id, Assessment.overall).join(
            latest, (latest.c.instance_id == Assessment.instance_id) & (latest.c.at == Assessment.assessed_at)
        )
    ).all()
    return dict(rows)


def to_read(inst: PlantInstance, rating: int | None = None) -> InstanceRead:
    spot = inst.current_spot
    return InstanceRead.model_validate(inst).model_copy(
        update={
            "plant_name": inst.plant.common_name if inst.plant else None,
            "plant_image_media_id": inst.plant.image_media_id if inst.plant else None,
            "spot_name": spot.name if spot else None,
            "area_id": spot.area_id if spot else None,
            "area_name": spot.area.name if spot else None,
            "position_label": inst.current_position.label if inst.current_position else None,
            "latest_overall_rating": rating,
        }
    )


def list_instance_reads(db: Session, stmt: Select) -> list[InstanceRead]:
    instances = list(db.scalars(stmt.options(*_LOAD)))
    ratings = _latest_ratings(db, [i.id for i in instances])
    return [to_read(i, ratings.get(i.id)) for i in instances]


def _load(db: Session, instance_id: int) -> PlantInstance:
    inst = db.scalar(select(PlantInstance).where(PlantInstance.id == instance_id).options(*_LOAD))
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Instance {instance_id} not found")
    return inst


def _detail(db: Session, instance_id: int) -> InstanceDetail:
    db.expire_all()
    inst = db.scalar(
        select(PlantInstance)
        .where(PlantInstance.id == instance_id)
        .options(
            *_LOAD,
            selectinload(PlantInstance.placements).selectinload(Placement.spot).selectinload(Spot.area),
            selectinload(PlantInstance.placements).selectinload(Placement.position),
        )
    )
    assert inst is not None
    placements = [
        PlacementRead.model_validate(p).model_copy(
            update={
                "spot_name": p.spot.name if p.spot else None,
                "area_name": p.spot.area.name if p.spot else None,
                "position_label": p.position.label if p.position else None,
            }
        )
        for p in inst.placements
    ]
    children = list(db.scalars(select(PlantInstance.id).where(PlantInstance.parent_instance_id == inst.id)))
    base = to_read(inst, _latest_ratings(db, [inst.id]).get(inst.id))
    return InstanceDetail(**base.model_dump(), placements=placements, children_ids=children)


@router.get("", response_model=Page[InstanceRead])
def list_instances(
    db: DB,
    _: CurrentUser,
    status_: list[InstanceStatus] | None = Query(None, alias="status", description="Default: all statuses"),
    plant_id: int | None = None,
    area_id: int | None = None,
    spot_id: int | None = None,
    q: str | None = Query(None, description="Search plant name or nickname"),
    sort: Literal["plant", "-created_at", "acquired_date", "-acquired_date"] = "plant",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[InstanceRead]:
    stmt = select(PlantInstance).join(Plant, Plant.id == PlantInstance.plant_id)
    if status_:
        stmt = stmt.where(PlantInstance.status.in_([s.value for s in status_]))
    if plant_id is not None:
        stmt = stmt.where(PlantInstance.plant_id == plant_id)
    if spot_id is not None:
        stmt = stmt.where(PlantInstance.current_spot_id == spot_id)
    if area_id is not None:
        stmt = stmt.join(Spot, Spot.id == PlantInstance.current_spot_id).where(Spot.area_id == area_id)
    if q:
        stmt = stmt.where(or_(Plant.common_name.ilike(f"%{q}%"), PlantInstance.nickname.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {
        "plant": (Plant.common_name, PlantInstance.id),
        "-created_at": (PlantInstance.created_at.desc(),),
        "acquired_date": (PlantInstance.acquired_date,),
        "-acquired_date": (PlantInstance.acquired_date.desc(),),
    }[sort]
    items = list_instance_reads(db, stmt.order_by(*order).limit(limit).offset(offset))
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "",
    response_model=InstanceDetail,
    status_code=201,
    summary="Add a plant instance, optionally placing it (records an 'acquired' or 'planted' event)",
)
def create_instance(payload: InstanceCreate, db: DB, user: CurrentUser) -> InstanceDetail:
    inst = svc.create_instance(db, payload, user)
    db.commit()
    return _detail(db, inst.id)


@router.get("/{instance_id}", response_model=InstanceDetail)
def get_instance(instance_id: int, db: DB, _: CurrentUser) -> InstanceDetail:
    _load(db, instance_id)
    return _detail(db, instance_id)


@router.patch(
    "/{instance_id}",
    response_model=InstanceDetail,
    summary="Edit descriptive fields. Use the action endpoints to move, retire etc.",
)
def update_instance(instance_id: int, payload: InstanceUpdate, db: DB, _: CurrentUser) -> InstanceDetail:
    inst = _load(db, instance_id)
    changes = payload.model_dump(exclude_unset=True, exclude={"attributes"})
    if changes.get("plant_id") is not None and db.get(Plant, changes["plant_id"]) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Plant {changes['plant_id']} does not exist")
    if changes.get("parent_instance_id") is not None:
        if changes["parent_instance_id"] == inst.id or db.get(PlantInstance, changes["parent_instance_id"]) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid parent_instance_id")
    for key, value in changes.items():
        if value is None and key in ("plant_id", "quantity"):
            continue
        setattr(inst, key, value)
    if payload.attributes is not None:
        inst.attributes = validate_attributes(db, "instance", payload.attributes, inst.attributes)
    db.commit()
    return _detail(db, instance_id)


@router.delete(
    "/{instance_id}",
    status_code=204,
    summary="Permanently delete an instance and its history. Prefer /retire to keep the record.",
)
def delete_instance(instance_id: int, db: DB, _: CurrentUser) -> None:
    inst = _load(db, instance_id)
    for m in db.scalars(select(Media).where(Media.instance_id == instance_id)):
        media_service.delete_files(m)
    db.delete(inst)
    db.commit()


# ---- Actions ---------------------------------------------------------------


@router.post("/{instance_id}/move", response_model=InstanceDetail, tags=["instance actions"])
def move_instance(instance_id: int, payload: MoveRequest, db: DB, user: CurrentUser) -> InstanceDetail:
    svc.move(db, _load(db, instance_id), payload, user)
    db.commit()
    return _detail(db, instance_id)


@router.post(
    "/{instance_id}/transplant",
    response_model=InstanceDetail,
    tags=["instance actions"],
    summary="Move into new ground or a new container (records pot size / soil)",
)
def transplant_instance(instance_id: int, payload: TransplantRequest, db: DB, user: CurrentUser) -> InstanceDetail:
    svc.move(db, _load(db, instance_id), payload, user, event_type=EventType.transplanted)
    db.commit()
    return _detail(db, instance_id)


@router.post(
    "/{instance_id}/repot",
    response_model=InstanceDetail,
    tags=["instance actions"],
    summary="Repot without changing location",
)
def repot_instance(instance_id: int, payload: RepotRequest, db: DB, user: CurrentUser) -> InstanceDetail:
    svc.repot(db, _load(db, instance_id), payload, user)
    db.commit()
    return _detail(db, instance_id)


@router.post(
    "/{instance_id}/retire",
    response_model=InstanceDetail,
    tags=["instance actions"],
    summary="Record a death, removal or give-away, with an optional final assessment",
)
def retire_instance(instance_id: int, payload: RetireRequest, db: DB, user: CurrentUser) -> InstanceDetail:
    svc.retire(db, _load(db, instance_id), payload, user)
    db.commit()
    return _detail(db, instance_id)


@router.post("/{instance_id}/revive", response_model=InstanceDetail, tags=["instance actions"])
def revive_instance(instance_id: int, payload: ReviveRequest, db: DB, user: CurrentUser) -> InstanceDetail:
    svc.revive(db, _load(db, instance_id), payload, user)
    db.commit()
    return _detail(db, instance_id)


@router.post(
    "/{instance_id}/propagate",
    response_model=InstanceDetail,
    status_code=201,
    tags=["instance actions"],
    summary="Create a new instance from a cutting/division/seed of this one. Returns the new instance.",
)
def propagate_instance(instance_id: int, payload: PropagateRequest, db: DB, user: CurrentUser) -> InstanceDetail:
    child = svc.propagate(db, _load(db, instance_id), payload, user)
    db.commit()
    return _detail(db, child.id)


@router.post(
    "/{instance_id}/assess",
    response_model=AssessmentRead,
    status_code=201,
    tags=["instance actions"],
    summary="Record how well the plant is doing",
)
def assess_instance(instance_id: int, payload: AssessRequest, db: DB, user: CurrentUser) -> Assessment:
    assessment = svc.record_assessment(db, _load(db, instance_id), payload, payload.assessed_at, user)
    db.commit()
    return assessment


# ---- History ---------------------------------------------------------------


@router.get("/{instance_id}/placements", response_model=list[PlacementRead])
def instance_placements(instance_id: int, db: DB, _: CurrentUser) -> list[PlacementRead]:
    _load(db, instance_id)
    return _detail(db, instance_id).placements


@router.get(
    "/{instance_id}/timeline",
    response_model=list[TimelineEntry],
    summary="Events (newest first) with their assessments and photos",
)
def instance_timeline(instance_id: int, db: DB, _: CurrentUser) -> list[TimelineEntry]:
    get_or_404(db, PlantInstance, instance_id, "Instance")
    events = list(
        db.scalars(
            select(InstanceEvent)
            .where(InstanceEvent.instance_id == instance_id)
            .order_by(InstanceEvent.occurred_at.desc(), InstanceEvent.id.desc())
        )
    )
    assessments = {
        a.event_id: a for a in db.scalars(select(Assessment).where(Assessment.instance_id == instance_id)) if a.event_id
    }
    media_by_event: dict[int, list[Media]] = {}
    for m in db.scalars(select(Media).where(Media.instance_id == instance_id, Media.event_id.is_not(None))):
        media_by_event.setdefault(m.event_id, []).append(m)
    return [
        TimelineEntry(
            event=EventRead.model_validate(e),
            assessment=AssessmentRead.model_validate(assessments[e.id]) if e.id in assessments else None,
            media=[MediaRead.model_validate(m) for m in media_by_event.get(e.id, [])],
        )
        for e in events
    ]
