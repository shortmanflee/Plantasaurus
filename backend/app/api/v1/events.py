from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.auth.deps import DB, CurrentUser
from app.db import as_utc, utcnow
from app.models import InstanceEvent, PlantInstance
from app.models.enums import SYSTEM_EVENT_TYPES, EventType
from app.schemas.common import Page
from app.schemas.instance import EventCreate, EventRead, EventUpdate
from app.services.crud import get_or_404, paginate

router = APIRouter(prefix="/events", tags=["events"])

_ACTION_HINT = (
    "'{t}' events change placement, status or assessments and must be created via the "
    "/instances/{{id}}/move|transplant|repot|retire|revive|propagate|assess endpoints"
)


@router.get("", response_model=Page[EventRead])
def list_events(
    db: DB,
    _: CurrentUser,
    instance_id: int | None = None,
    event_type: list[EventType] | None = Query(None),
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[EventRead]:
    stmt = select(InstanceEvent).order_by(InstanceEvent.occurred_at.desc(), InstanceEvent.id.desc())
    if instance_id is not None:
        stmt = stmt.where(InstanceEvent.instance_id == instance_id)
    if event_type:
        stmt = stmt.where(InstanceEvent.event_type.in_([t.value for t in event_type]))
    if since:
        stmt = stmt.where(InstanceEvent.occurred_at >= as_utc(since))
    if until:
        stmt = stmt.where(InstanceEvent.occurred_at <= as_utc(until))
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "",
    response_model=EventRead,
    status_code=201,
    summary="Log a care/growth/note event (watered, fed, pruned, pest_disease, treated, flowered, fruited, harvested, photo, note)",
)
def create_event(payload: EventCreate, db: DB, user: CurrentUser) -> InstanceEvent:
    if payload.event_type in SYSTEM_EVENT_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _ACTION_HINT.format(t=payload.event_type.value))
    get_or_404(db, PlantInstance, payload.instance_id, "Instance")
    when = as_utc(payload.occurred_at) if payload.occurred_at else utcnow()
    if when > utcnow():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "occurred_at cannot be in the future")
    event = InstanceEvent(
        instance_id=payload.instance_id,
        event_type=payload.event_type.value,
        occurred_at=when,
        user_id=user.id,
        notes=payload.notes,
        data=payload.data,
    )
    db.add(event)
    db.commit()
    return event


@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: int, db: DB, _: CurrentUser) -> InstanceEvent:
    return get_or_404(db, InstanceEvent, event_id, "Event")


@router.patch(
    "/{event_id}",
    response_model=EventRead,
    summary="Edit an event. Lifecycle events only allow notes to change, to keep history consistent.",
)
def update_event(event_id: int, payload: EventUpdate, db: DB, _: CurrentUser) -> InstanceEvent:
    event = get_or_404(db, InstanceEvent, event_id, "Event")
    changes = payload.model_dump(exclude_unset=True)
    if EventType(event.event_type) in SYSTEM_EVENT_TYPES and set(changes) - {"notes"}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Only notes can be edited on lifecycle/assessment events"
        )
    if changes.get("occurred_at"):
        when = as_utc(changes["occurred_at"])
        if when > utcnow():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "occurred_at cannot be in the future")
        event.occurred_at = when
    if "notes" in changes:
        event.notes = changes["notes"]
    if changes.get("data") is not None:
        event.data = changes["data"]
    db.commit()
    return event


@router.delete(
    "/{event_id}",
    status_code=204,
    summary="Delete a care/note event. Lifecycle events cannot be deleted (history is append-only).",
)
def delete_event(event_id: int, db: DB, _: CurrentUser) -> None:
    event = get_or_404(db, InstanceEvent, event_id, "Event")
    if EventType(event.event_type) in SYSTEM_EVENT_TYPES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Lifecycle events are part of the placement history and cannot be deleted",
        )
    db.delete(event)
    db.commit()
