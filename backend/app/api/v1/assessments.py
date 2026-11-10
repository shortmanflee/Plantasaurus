from fastapi import APIRouter, Query
from sqlalchemy import select

from app.auth.deps import DB, CurrentUser
from app.db import as_utc
from app.models import Assessment, InstanceEvent, PlantInstance
from app.schemas.common import Page
from app.schemas.instance import AssessmentCreate, AssessmentRead, AssessmentUpdate
from app.services import placement as svc
from app.services.crud import get_or_404, paginate

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.get("", response_model=Page[AssessmentRead])
def list_assessments(
    db: DB,
    _: CurrentUser,
    instance_id: int | None = None,
    plant_id: int | None = None,
    spot_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[AssessmentRead]:
    from app.models import Placement

    stmt = select(Assessment).order_by(Assessment.assessed_at.desc())
    if instance_id is not None:
        stmt = stmt.where(Assessment.instance_id == instance_id)
    if plant_id is not None:
        stmt = stmt.join(PlantInstance, PlantInstance.id == Assessment.instance_id).where(
            PlantInstance.plant_id == plant_id
        )
    if spot_id is not None:
        stmt = stmt.join(Placement, Placement.id == Assessment.placement_id).where(Placement.spot_id == spot_id)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=AssessmentRead, status_code=201)
def create_assessment(payload: AssessmentCreate, db: DB, user: CurrentUser) -> Assessment:
    instance = get_or_404(db, PlantInstance, payload.instance_id, "Instance")
    assessment = svc.record_assessment(db, instance, payload, payload.assessed_at, user)
    db.commit()
    return assessment


@router.get("/{assessment_id}", response_model=AssessmentRead)
def get_assessment(assessment_id: int, db: DB, _: CurrentUser) -> Assessment:
    return get_or_404(db, Assessment, assessment_id)


@router.patch("/{assessment_id}", response_model=AssessmentRead)
def update_assessment(assessment_id: int, payload: AssessmentUpdate, db: DB, _: CurrentUser) -> Assessment:
    assessment = get_or_404(db, Assessment, assessment_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("assessed_at"):
        when = as_utc(changes.pop("assessed_at"))
        assessment.assessed_at = when
        placement = svc.placement_at(db, assessment.instance_id, when)
        assessment.placement_id = placement.id if placement else None
    else:
        changes.pop("assessed_at", None)
    for key, value in changes.items():
        setattr(assessment, key, value)
    if assessment.event_id and (event := db.get(InstanceEvent, assessment.event_id)):
        event.occurred_at = assessment.assessed_at
        event.notes = assessment.notes
        event.data = {
            k: v
            for k, v in AssessmentUpdate.model_validate(assessment, from_attributes=True)
            .model_dump(mode="json", exclude={"notes", "assessed_at"}, exclude_none=True)
            .items()
        } | ({"final": True} if assessment.is_final else {})
    db.commit()
    return assessment


@router.delete("/{assessment_id}", status_code=204)
def delete_assessment(assessment_id: int, db: DB, _: CurrentUser) -> None:
    assessment = get_or_404(db, Assessment, assessment_id)
    if assessment.event_id and (event := db.get(InstanceEvent, assessment.event_id)):
        db.delete(event)
    db.delete(assessment)
    db.commit()
