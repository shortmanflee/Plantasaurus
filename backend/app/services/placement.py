"""Transactional lifecycle operations for plant instances.

Every operation that changes where an instance lives, or its status, goes through
this module so that `PlantInstance.current_*`, the `Placement` history and the
`InstanceEvent` timeline always agree.
"""

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import as_utc, utcnow
from app.models import Assessment, InstanceEvent, Placement, Plant, PlantInstance, Position, Spot, User
from app.models.enums import EventType, InstanceSource, InstanceStatus
from app.schemas.instance import (
    AssessmentInput,
    InstanceCreate,
    MoveRequest,
    PropagateRequest,
    RepotRequest,
    RetireRequest,
    ReviveRequest,
    TransplantRequest,
)
from app.services.custom_fields import validate_attributes


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def _when(value: datetime | None) -> datetime:
    when = as_utc(value) if value else utcnow()
    if when > utcnow():
        raise _unprocessable("occurred_at cannot be in the future")
    return when


def resolve_target(db: Session, spot_id: int | None, position_id: int | None) -> tuple[int | None, int | None]:
    """Validate a spot/position pair. A position on its own implies its spot."""
    if position_id is not None:
        position = db.get(Position, position_id)
        if position is None:
            raise _unprocessable(f"Position {position_id} does not exist")
        if spot_id is not None and position.spot_id != spot_id:
            raise _unprocessable(f"Position {position_id} is not in spot {spot_id}")
        spot_id = position.spot_id
    if spot_id is not None:
        spot = db.get(Spot, spot_id)
        if spot is None:
            raise _unprocessable(f"Spot {spot_id} does not exist")
        if spot.archived:
            raise _unprocessable(f"Spot '{spot.name}' is archived")
    return spot_id, position_id


def current_placement(db: Session, instance: PlantInstance) -> Placement | None:
    return db.scalar(
        select(Placement)
        .where(Placement.instance_id == instance.id, Placement.ended_at.is_(None))
        .order_by(Placement.started_at.desc())
    )


def placement_at(db: Session, instance_id: int, when: datetime) -> Placement | None:
    """The placement an instance was in at a point in time."""
    return db.scalar(
        select(Placement)
        .where(
            Placement.instance_id == instance_id,
            Placement.started_at <= when,
            (Placement.ended_at.is_(None)) | (Placement.ended_at > when),
        )
        .order_by(Placement.started_at.desc())
    )


def _add_event(
    db: Session,
    instance: PlantInstance,
    event_type: EventType,
    when: datetime,
    user: User | None,
    notes: str | None = None,
    data: dict[str, Any] | None = None,
    **locations: int | None,
) -> InstanceEvent:
    event = InstanceEvent(
        instance_id=instance.id,
        event_type=event_type.value,
        occurred_at=when,
        user_id=user.id if user else None,
        notes=notes,
        data={k: v for k, v in (data or {}).items() if v is not None},
        **locations,
    )
    db.add(event)
    db.flush()
    return event


def _require_active(instance: PlantInstance) -> None:
    if instance.status != InstanceStatus.active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Instance {instance.id} is {instance.status}; revive it before making changes",
        )


def _check_chronology(db: Session, instance: PlantInstance, when: datetime) -> Placement | None:
    current = current_placement(db, instance)
    if current is not None and when < current.started_at:
        raise _unprocessable(
            f"occurred_at is before the current placement started ({current.started_at.isoformat()})"
        )
    return current


def _relocate(
    db: Session,
    instance: PlantInstance,
    spot_id: int | None,
    position_id: int | None,
    when: datetime,
    event: InstanceEvent,
    current: Placement | None,
) -> None:
    if current is not None:
        current.ended_at = when
        current.end_event_id = event.id
    if spot_id is not None:
        db.add(
            Placement(
                instance_id=instance.id,
                spot_id=spot_id,
                position_id=position_id,
                started_at=when,
                start_event_id=event.id,
            )
        )
    instance.current_spot_id = spot_id
    instance.current_position_id = position_id


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def create_instance(db: Session, payload: InstanceCreate, user: User | None) -> PlantInstance:
    if db.get(Plant, payload.plant_id) is None:
        raise _unprocessable(f"Plant {payload.plant_id} does not exist")
    if payload.parent_instance_id is not None and db.get(PlantInstance, payload.parent_instance_id) is None:
        raise _unprocessable(f"Parent instance {payload.parent_instance_id} does not exist")
    spot_id, position_id = resolve_target(db, payload.spot_id, payload.position_id)
    when = _when(payload.occurred_at)

    fields = payload.model_dump(
        exclude={"spot_id", "position_id", "occurred_at", "event_notes", "attributes"}
    )
    instance = PlantInstance(
        **fields,
        attributes=validate_attributes(db, "instance", payload.attributes),
        status=InstanceStatus.active.value,
    )
    if instance.acquired_date is None:
        instance.acquired_date = when.date()
    db.add(instance)
    db.flush()

    event_type = EventType.planted if spot_id is not None else EventType.acquired
    event = _add_event(
        db,
        instance,
        event_type,
        when,
        user,
        notes=payload.event_notes,
        data={"source": payload.source, "source_detail": payload.source_detail, "cost": payload.cost},
        to_spot_id=spot_id,
        to_position_id=position_id,
    )
    _relocate(db, instance, spot_id, position_id, when, event, None)
    return instance


def move(
    db: Session,
    instance: PlantInstance,
    payload: MoveRequest,
    user: User | None,
    event_type: EventType = EventType.moved,
) -> InstanceEvent:
    _require_active(instance)
    spot_id, position_id = resolve_target(db, payload.spot_id, payload.position_id)
    if spot_id is None:
        raise _unprocessable("A destination spot_id or position_id is required")
    if spot_id == instance.current_spot_id and position_id == instance.current_position_id:
        raise _unprocessable("Instance is already in that location")
    when = _when(payload.occurred_at)
    current = _check_chronology(db, instance, when)

    data = dict(payload.data)
    if isinstance(payload, TransplantRequest):
        data.update(pot_size=payload.pot_size, soil=payload.soil)
    event = _add_event(
        db,
        instance,
        event_type,
        when,
        user,
        notes=payload.notes,
        data=data,
        from_spot_id=instance.current_spot_id,
        from_position_id=instance.current_position_id,
        to_spot_id=spot_id,
        to_position_id=position_id,
    )
    _relocate(db, instance, spot_id, position_id, when, event, current)
    return event


def repot(db: Session, instance: PlantInstance, payload: RepotRequest, user: User | None) -> InstanceEvent:
    _require_active(instance)
    when = _when(payload.occurred_at)
    data = {**payload.data, "pot_size": payload.pot_size, "soil": payload.soil}
    return _add_event(db, instance, EventType.repotted, when, user, notes=payload.notes, data=data)


def record_assessment(
    db: Session,
    instance: PlantInstance,
    payload: AssessmentInput,
    when: datetime | None,
    user: User | None,
    is_final: bool = False,
) -> Assessment:
    when = _when(when)
    placement = placement_at(db, instance.id, when)
    fields = payload.model_dump(include=set(AssessmentInput.model_fields))
    data = payload.model_dump(mode="json", include=set(AssessmentInput.model_fields) - {"notes"}, exclude_none=True)
    if is_final:
        data["final"] = True
    event = _add_event(db, instance, EventType.assessment, when, user, notes=payload.notes, data=data)
    assessment = Assessment(
        instance_id=instance.id,
        placement_id=placement.id if placement else None,
        event_id=event.id,
        user_id=user.id if user else None,
        assessed_at=when,
        is_final=is_final,
        **fields,
    )
    db.add(assessment)
    db.flush()
    return assessment


def retire(db: Session, instance: PlantInstance, payload: RetireRequest, user: User | None) -> InstanceEvent:
    _require_active(instance)
    if payload.status == InstanceStatus.active:
        raise _unprocessable("status must be dead, removed or given_away")
    when = _when(payload.occurred_at)
    current = _check_chronology(db, instance, when)

    if payload.final_assessment is not None:
        record_assessment(db, instance, payload.final_assessment, when, user, is_final=True)

    event_type = EventType(payload.status.value if payload.status != InstanceStatus.dead else "died")
    event = _add_event(
        db,
        instance,
        event_type,
        when,
        user,
        notes=payload.notes,
        data={**payload.data, "reason": payload.reason},
        from_spot_id=instance.current_spot_id,
        from_position_id=instance.current_position_id,
    )
    _relocate(db, instance, None, None, when, event, current)
    instance.status = payload.status.value
    instance.ended_at = when
    instance.end_reason = payload.reason
    return event


def revive(db: Session, instance: PlantInstance, payload: ReviveRequest, user: User | None) -> InstanceEvent:
    """Undo a retirement (e.g. recorded as dead by mistake, or it resprouted)."""
    if instance.status == InstanceStatus.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Instance is already active")
    spot_id, position_id = resolve_target(db, payload.spot_id, payload.position_id)
    when = _when(payload.occurred_at)
    if instance.ended_at and when < instance.ended_at:
        raise _unprocessable("occurred_at is before the instance was retired")
    event = _add_event(
        db,
        instance,
        EventType.revived,
        when,
        user,
        notes=payload.notes,
        data={**payload.data, "previous_status": instance.status},
        to_spot_id=spot_id,
        to_position_id=position_id,
    )
    _relocate(db, instance, spot_id, position_id, when, event, None)
    instance.status = InstanceStatus.active.value
    instance.ended_at = None
    instance.end_reason = None
    return event


def propagate(
    db: Session, parent: PlantInstance, payload: PropagateRequest, user: User | None
) -> PlantInstance:
    _require_active(parent)
    if payload.method not in (InstanceSource.cutting, InstanceSource.division, InstanceSource.seed):
        raise _unprocessable("method must be cutting, division or seed")
    when = _when(payload.occurred_at)
    child = create_instance(
        db,
        InstanceCreate(
            plant_id=parent.plant_id,
            nickname=payload.nickname,
            quantity=payload.quantity,
            source=payload.method,
            source_detail=f"Propagated from instance #{parent.id}",
            parent_instance_id=parent.id,
            spot_id=payload.spot_id,
            position_id=payload.position_id,
            occurred_at=when,
            event_notes=payload.notes,
        ),
        user,
    )
    _add_event(
        db,
        parent,
        EventType.propagated,
        when,
        user,
        notes=payload.notes,
        data={**payload.data, "child_instance_id": child.id, "method": payload.method.value, "quantity": payload.quantity},
    )
    return child
