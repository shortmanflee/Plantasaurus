from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import (
    EventType,
    InstanceSource,
    InstanceStatus,
    KeepLocation,
    YesNoMaybe,
)
from app.schemas.common import ORMModel, ResponseModel, Timestamps
from app.schemas.media import MediaRead


# ---- Placement -------------------------------------------------------------
class PlacementTarget(BaseModel):
    spot_id: int | None = None
    position_id: int | None = Field(
        default=None, description="If given without spot_id, the spot is inferred from the position."
    )


class PlacementRead(ORMModel):
    id: int
    instance_id: int
    spot_id: int | None
    position_id: int | None
    started_at: datetime
    ended_at: datetime | None
    start_event_id: int | None
    end_event_id: int | None
    spot_name: str | None = None
    area_name: str | None = None
    position_label: str | None = None


# ---- Instance --------------------------------------------------------------
class InstanceBase(BaseModel):
    nickname: str | None = None
    quantity: int = Field(default=1, ge=1)
    acquired_date: date | None = None
    source: InstanceSource | None = None
    source_detail: str | None = None
    cost: float | None = Field(default=None, ge=0)
    parent_instance_id: int | None = None
    notes: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class InstanceCreate(InstanceBase, PlacementTarget):
    plant_id: int
    occurred_at: datetime | None = Field(default=None, description="When acquired/planted; defaults to now")
    event_notes: str | None = None


class InstanceUpdate(BaseModel):
    """Edit descriptive fields. Use action endpoints to change placement or status."""

    plant_id: int | None = None
    nickname: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    acquired_date: date | None = None
    source: InstanceSource | None = None
    source_detail: str | None = None
    cost: float | None = Field(default=None, ge=0)
    parent_instance_id: int | None = None
    notes: str | None = None
    end_reason: str | None = None
    attributes: dict[str, Any] | None = None


class InstanceRead(InstanceBase, Timestamps):
    id: int
    plant_id: int
    status: InstanceStatus
    current_spot_id: int | None
    current_position_id: int | None
    ended_at: datetime | None
    end_reason: str | None
    plant_name: str | None = None
    plant_image_media_id: int | None = None
    area_id: int | None = None
    area_name: str | None = None
    spot_name: str | None = None
    position_label: str | None = None
    latest_overall_rating: int | None = None


# ---- Actions ---------------------------------------------------------------
class ActionBase(BaseModel):
    occurred_at: datetime | None = None
    notes: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class MoveRequest(ActionBase, PlacementTarget):
    pass


class TransplantRequest(MoveRequest):
    pot_size: str | None = None
    soil: str | None = None


class RepotRequest(ActionBase):
    pot_size: str | None = None
    soil: str | None = None


class AssessmentInput(BaseModel):
    health: int | None = Field(default=None, ge=1, le=5)
    vigour: int | None = Field(default=None, ge=1, le=5)
    flowering_fruiting: int | None = Field(default=None, ge=1, le=5)
    overall: int | None = Field(default=None, ge=1, le=5)
    would_buy_again: YesNoMaybe | None = None
    would_keep_location: KeepLocation | None = None
    notes: str | None = None


class RetireRequest(ActionBase):
    status: InstanceStatus = Field(description="dead, removed or given_away")
    reason: str | None = Field(default=None, description="e.g. frost, overwatering, pests, too shady")
    final_assessment: AssessmentInput | None = None


class ReviveRequest(ActionBase, PlacementTarget):
    pass


class PropagateRequest(ActionBase, PlacementTarget):
    method: InstanceSource = InstanceSource.cutting
    nickname: str | None = None
    quantity: int = Field(default=1, ge=1)


# ---- Events ----------------------------------------------------------------
class EventCreate(BaseModel):
    instance_id: int
    event_type: EventType
    occurred_at: datetime | None = None
    notes: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class EventUpdate(BaseModel):
    occurred_at: datetime | None = None
    notes: str | None = None
    data: dict[str, Any] | None = None


class EventRead(Timestamps):
    id: int
    instance_id: int
    event_type: EventType
    occurred_at: datetime
    user_id: int | None
    notes: str | None
    data: dict[str, Any]
    from_spot_id: int | None
    from_position_id: int | None
    to_spot_id: int | None
    to_position_id: int | None


# ---- Assessments -----------------------------------------------------------
class AssessRequest(AssessmentInput):
    assessed_at: datetime | None = None


class AssessmentCreate(AssessRequest):
    instance_id: int


class AssessmentUpdate(AssessmentInput):
    assessed_at: datetime | None = None


class AssessmentRead(AssessmentInput, Timestamps):
    id: int
    instance_id: int
    placement_id: int | None
    event_id: int | None
    user_id: int | None
    assessed_at: datetime
    is_final: bool


# ---- Timeline --------------------------------------------------------------
class TimelineEntry(ResponseModel):
    event: EventRead
    assessment: AssessmentRead | None = None
    media: list[MediaRead] = Field(default_factory=list)


class InstanceDetail(InstanceRead):
    placements: list[PlacementRead]
    children_ids: list[int] = Field(default_factory=list)
