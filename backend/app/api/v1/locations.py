from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth.deps import DB, CurrentUser
from app.models import Area, Media, Placement, PlantInstance, Position, Spot
from app.models.enums import Environment, InstanceStatus
from app.schemas.location import (
    AreaCreate,
    AreaNode,
    AreaRead,
    AreaUpdate,
    OccupantSummary,
    PositionCreate,
    PositionNode,
    PositionRead,
    PositionUpdate,
    SpotCreate,
    SpotNode,
    SpotRead,
    SpotUpdate,
)
from app.services.crud import apply_update, commit, ensure_exists, get_or_404
from app.services.custom_fields import validate_attributes
from app.services.homeassistant import validate_assignment
from app.services.insights import SpotInsights, spot_insights

router = APIRouter(tags=["locations"])


def _occupied(db: Session, *, spot_id: int | None = None, position_id: int | None = None, area_id: int | None = None) -> bool:
    stmt = select(PlantInstance.id).where(PlantInstance.status == InstanceStatus.active.value)
    if spot_id is not None:
        stmt = stmt.where(PlantInstance.current_spot_id == spot_id)
    if position_id is not None:
        stmt = stmt.where(PlantInstance.current_position_id == position_id)
    if area_id is not None:
        stmt = stmt.join(Spot, Spot.id == PlantInstance.current_spot_id).where(Spot.area_id == area_id)
    return db.scalar(stmt.limit(1)) is not None


def _has_history(db: Session, *, spot_ids: list[int] | None = None, position_id: int | None = None) -> bool:
    stmt = select(Placement.id)
    if spot_ids is not None:
        stmt = stmt.where(Placement.spot_id.in_(spot_ids))
    if position_id is not None:
        stmt = stmt.where(Placement.position_id == position_id)
    return db.scalar(stmt.limit(1)) is not None


# ---- Areas -----------------------------------------------------------------


@router.get("/areas", response_model=list[AreaRead])
def list_areas(db: DB, _: CurrentUser, environment: Environment | None = None) -> list[Area]:
    stmt = select(Area).order_by(Area.sort_order, Area.name)
    if environment:
        stmt = stmt.where(Area.environment == environment.value)
    return list(db.scalars(stmt))


@router.post("/areas", response_model=AreaRead, status_code=201)
def create_area(payload: AreaCreate, db: DB, _: CurrentUser) -> Area:
    ensure_exists(db, Media, payload.image_media_id, "Media")
    area = Area(**payload.model_dump(mode="json", exclude={"attributes"}))
    area.attributes = validate_attributes(db, "area", payload.attributes)
    db.add(area)
    commit(db, f"An area named '{payload.name}' already exists")
    return area


@router.get("/areas/{area_id}", response_model=AreaRead)
def get_area(area_id: int, db: DB, _: CurrentUser) -> Area:
    return get_or_404(db, Area, area_id)


@router.patch("/areas/{area_id}", response_model=AreaRead)
def update_area(area_id: int, payload: AreaUpdate, db: DB, _: CurrentUser) -> Area:
    area = get_or_404(db, Area, area_id)
    ensure_exists(db, Media, payload.image_media_id, "Media")
    for key, value in payload.model_dump(mode="json", exclude_unset=True, exclude={"attributes"}).items():
        if value is None and key in ("name", "environment", "sort_order"):
            continue
        setattr(area, key, value)
    if payload.attributes is not None:
        area.attributes = validate_attributes(db, "area", payload.attributes, area.attributes)
    commit(db, "An area with that name already exists")
    return area


@router.delete(
    "/areas/{area_id}",
    status_code=204,
    summary="Delete an area and its spots. Refused if any plant currently lives there, or if history exists (unless force=true).",
)
def delete_area(area_id: int, db: DB, _: CurrentUser, force: bool = False) -> None:
    area = get_or_404(db, Area, area_id)
    if _occupied(db, area_id=area_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Area has active plants; move them first")
    if not force and _has_history(db, spot_ids=[s.id for s in area.spots]):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Area has placement history. Archive its spots instead, or pass force=true to delete anyway.",
        )
    db.delete(area)
    db.commit()


@router.get("/areas/{area_id}/spots", response_model=list[SpotRead])
def area_spots(area_id: int, db: DB, _: CurrentUser, include_archived: bool = False) -> list[Spot]:
    get_or_404(db, Area, area_id)
    stmt = select(Spot).where(Spot.area_id == area_id).order_by(Spot.sort_order, Spot.name)
    if not include_archived:
        stmt = stmt.where(Spot.archived.is_(False))
    return list(db.scalars(stmt))


# ---- Spots -----------------------------------------------------------------


@router.get("/spots", response_model=list[SpotRead])
def list_spots(
    db: DB,
    _: CurrentUser,
    area_id: int | None = None,
    include_archived: bool = False,
    q: str | None = Query(None, description="Search by name"),
) -> list[Spot]:
    stmt = select(Spot).order_by(Spot.area_id, Spot.sort_order, Spot.name)
    if area_id is not None:
        stmt = stmt.where(Spot.area_id == area_id)
    if not include_archived:
        stmt = stmt.where(Spot.archived.is_(False))
    if q:
        stmt = stmt.where(Spot.name.ilike(f"%{q}%"))
    return list(db.scalars(stmt))


@router.post("/spots", response_model=SpotRead, status_code=201)
def create_spot(payload: SpotCreate, db: DB, _: CurrentUser) -> Spot:
    get_or_404(db, Area, payload.area_id)
    ensure_exists(db, Media, payload.image_media_id, "Media")
    validate_assignment(db, None, "irrigation_zone", payload.irrigation_zone_device_id)
    validate_assignment(db, None, "plant_monitor", payload.plant_monitor_device_id)
    spot = Spot(**payload.model_dump(mode="json", exclude={"attributes", "position_count"}))
    spot.attributes = validate_attributes(db, "spot", payload.attributes)
    spot.positions = [Position(label=str(i), sort_order=i) for i in range(1, payload.position_count + 1)]
    db.add(spot)
    commit(db, f"This area already has a spot named '{payload.name}'")
    db.refresh(spot, ["irrigation_zone_device", "plant_monitor_device"])
    return spot


@router.get("/spots/{spot_id}", response_model=SpotRead)
def get_spot(spot_id: int, db: DB, _: CurrentUser) -> Spot:
    return get_or_404(db, Spot, spot_id)


@router.patch("/spots/{spot_id}", response_model=SpotRead)
def update_spot(spot_id: int, payload: SpotUpdate, db: DB, _: CurrentUser) -> Spot:
    spot = get_or_404(db, Spot, spot_id)
    if payload.area_id is not None:
        get_or_404(db, Area, payload.area_id)
    ensure_exists(db, Media, payload.image_media_id, "Media")
    if payload.archived and _occupied(db, spot_id=spot_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Spot has active plants; move them before archiving")
    if "irrigation_zone_device_id" in payload.model_fields_set:
        validate_assignment(db, spot, "irrigation_zone", payload.irrigation_zone_device_id)
    if "plant_monitor_device_id" in payload.model_fields_set:
        validate_assignment(db, spot, "plant_monitor", payload.plant_monitor_device_id)
    for key, value in payload.model_dump(mode="json", exclude_unset=True, exclude={"attributes"}).items():
        if value is None and key in ("area_id", "name", "sort_order", "archived"):
            continue
        setattr(spot, key, value)
    if payload.attributes is not None:
        spot.attributes = validate_attributes(db, "spot", payload.attributes, spot.attributes)
    commit(db, "That area already has a spot with this name")
    db.refresh(spot, ["irrigation_zone_device", "plant_monitor_device"])
    return spot


@router.delete(
    "/spots/{spot_id}",
    status_code=204,
    summary="Delete a spot. Refused if occupied, or if it has history (archive it instead, or force=true).",
)
def delete_spot(spot_id: int, db: DB, _: CurrentUser, force: bool = False) -> None:
    spot = get_or_404(db, Spot, spot_id)
    if _occupied(db, spot_id=spot_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Spot has active plants; move them first")
    if not force and _has_history(db, spot_ids=[spot_id]):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Spot has placement history. Archive it instead, or pass force=true."
        )
    db.delete(spot)
    db.commit()


@router.get("/spots/{spot_id}/positions", response_model=list[PositionRead])
def spot_positions(spot_id: int, db: DB, _: CurrentUser) -> list[Position]:
    return get_or_404(db, Spot, spot_id).positions


@router.get("/spots/{spot_id}/insights", response_model=SpotInsights, tags=["insights"])
def get_spot_insights(spot_id: int, db: DB, _: CurrentUser) -> SpotInsights:
    return spot_insights(db, get_or_404(db, Spot, spot_id))


# ---- Positions -------------------------------------------------------------


@router.get("/positions", response_model=list[PositionRead])
def list_positions(db: DB, _: CurrentUser, spot_id: int | None = None) -> list[Position]:
    stmt = select(Position).order_by(Position.spot_id, Position.sort_order, Position.id)
    if spot_id is not None:
        stmt = stmt.where(Position.spot_id == spot_id)
    return list(db.scalars(stmt))


@router.post("/positions", response_model=PositionRead, status_code=201)
def create_position(payload: PositionCreate, db: DB, _: CurrentUser) -> Position:
    get_or_404(db, Spot, payload.spot_id)
    position = Position(**payload.model_dump())
    if position.sort_order is None:
        last = db.scalar(select(func.max(Position.sort_order)).where(Position.spot_id == payload.spot_id))
        position.sort_order = (last or 0) + 1
    db.add(position)
    commit(db, f"This spot already has a position labelled '{payload.label}'")
    return position


@router.get("/positions/{position_id}", response_model=PositionRead)
def get_position(position_id: int, db: DB, _: CurrentUser) -> Position:
    return get_or_404(db, Position, position_id)


@router.patch("/positions/{position_id}", response_model=PositionRead)
def update_position(position_id: int, payload: PositionUpdate, db: DB, _: CurrentUser) -> Position:
    position = get_or_404(db, Position, position_id)
    apply_update(position, payload)
    commit(db, "This spot already has a position with that label")
    return position


@router.delete("/positions/{position_id}", status_code=204)
def delete_position(position_id: int, db: DB, _: CurrentUser, force: bool = False) -> None:
    position = get_or_404(db, Position, position_id)
    if _occupied(db, position_id=position_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Position is occupied; move the plant first")
    if not force and _has_history(db, position_id=position_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Position has history; pass force=true to delete anyway")
    db.delete(position)
    db.commit()


# ---- Tree ------------------------------------------------------------------


@router.get("/locations/tree", response_model=list[AreaNode], summary="Full Area → Spot → Position tree with occupants")
def location_tree(db: DB, _: CurrentUser, include_archived: bool = False) -> list[AreaNode]:
    areas = list(
        db.scalars(
            select(Area)
            .order_by(Area.sort_order, Area.name)
            .options(selectinload(Area.spots).selectinload(Spot.positions))
        )
    )
    instances = db.scalars(
        select(PlantInstance)
        .where(PlantInstance.status == InstanceStatus.active.value, PlantInstance.current_spot_id.is_not(None))
        .options(selectinload(PlantInstance.plant))
    )
    by_spot: dict[int, list[OccupantSummary]] = defaultdict(list)
    for inst in instances:
        by_spot[inst.current_spot_id].append(
            OccupantSummary(
                instance_id=inst.id,
                plant_id=inst.plant_id,
                plant_name=inst.plant.common_name,
                nickname=inst.nickname,
                position_id=inst.current_position_id,
            )
        )

    tree = []
    for area in areas:
        spots = []
        for spot in area.spots:
            if spot.archived and not include_archived:
                continue
            occupants = by_spot.get(spot.id, [])
            spots.append(
                SpotNode(
                    **SpotRead.model_validate(spot).model_dump(),
                    positions=[
                        PositionNode(
                            id=p.id, label=p.label, occupants=[o for o in occupants if o.position_id == p.id]
                        )
                        for p in spot.positions
                    ],
                    unpositioned_occupants=[o for o in occupants if o.position_id is None],
                )
            )
        tree.append(AreaNode(**AreaRead.model_validate(area).model_dump(), spots=spots))
    return tree
