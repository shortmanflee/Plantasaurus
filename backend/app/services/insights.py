"""Read-only aggregations that help decide what to buy again and where to put it."""

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from app.schemas.common import ResponseModel as BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import utcnow
from app.models import Area, Assessment, InstanceEvent, Placement, Plant, PlantInstance, Spot
from app.models.enums import EventType, InstanceStatus

ASSESS_STALE_DAYS = 90


class RatingSummary(BaseModel):
    count: int = 0
    avg_overall: float | None = None
    avg_health: float | None = None
    avg_vigour: float | None = None
    avg_flowering_fruiting: float | None = None


class GroupPerformance(BaseModel):
    key: str
    label: str
    placements: int
    instances: int
    deaths: int
    avg_overall: float | None
    avg_days: float | None


class PlantInsights(BaseModel):
    plant_id: int
    instances_total: int
    status_counts: dict[str, int]
    survival_rate: float | None
    avg_lifespan_days_dead: float | None
    ratings: RatingSummary
    would_buy_again: dict[str, int]
    verdict: str
    by_spot: list[GroupPerformance]
    by_environment: list[GroupPerformance]
    by_aspect: list[GroupPerformance]
    by_sun_exposure: list[GroupPerformance]
    end_reasons: dict[str, int]


class SpotHistoryEntry(BaseModel):
    placement_id: int
    instance_id: int
    plant_id: int
    plant_name: str
    plant_image_media_id: int | None = None
    nickname: str | None
    position_label: str | None
    started_at: datetime
    ended_at: datetime | None
    days: float
    outcome: str
    avg_overall: float | None


class SpotInsights(BaseModel):
    spot_id: int
    current_count: int
    historic_count: int
    deaths: int
    avg_overall: float | None
    history: list[SpotHistoryEntry]


class RecentEvent(BaseModel):
    id: int
    instance_id: int
    event_type: str
    occurred_at: datetime
    notes: str | None
    plant_name: str
    nickname: str | None


class NeedsAssessment(BaseModel):
    instance_id: int
    plant_name: str
    nickname: str | None
    last_assessed_at: datetime | None


class Summary(BaseModel):
    plants: int
    active_instances: int
    areas: int
    spots: int
    status_counts: dict[str, int]
    recent_events: list[RecentEvent]
    recent_losses: list[RecentEvent]
    needs_assessment: list[NeedsAssessment]


def _avg(values: list[float | int | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(mean(vals), 2) if vals else None


def _rating_summary(assessments: list[Assessment]) -> RatingSummary:
    return RatingSummary(
        count=len(assessments),
        avg_overall=_avg([a.overall for a in assessments]),
        avg_health=_avg([a.health for a in assessments]),
        avg_vigour=_avg([a.vigour for a in assessments]),
        avg_flowering_fruiting=_avg([a.flowering_fruiting for a in assessments]),
    )


def plant_insights(db: Session, plant: Plant) -> PlantInsights:
    instances = list(
        db.scalars(
            select(PlantInstance)
            .where(PlantInstance.plant_id == plant.id)
            .options(selectinload(PlantInstance.placements).selectinload(Placement.spot).selectinload(Spot.area))
        )
    )
    ids = [i.id for i in instances]
    assessments = list(db.scalars(select(Assessment).where(Assessment.instance_id.in_(ids)))) if ids else []
    death_event_ids = (
        set(
            db.scalars(
                select(InstanceEvent.id).where(
                    InstanceEvent.instance_id.in_(ids), InstanceEvent.event_type == EventType.died.value
                )
            )
        )
        if ids
        else set()
    )

    status_counts: dict[str, int] = defaultdict(int)
    for inst in instances:
        status_counts[inst.status] += 1
    active, dead = status_counts[InstanceStatus.active], status_counts[InstanceStatus.dead]
    survival = round(active / (active + dead), 3) if active + dead else None

    lifespans = []
    for inst in instances:
        if inst.status == InstanceStatus.dead and inst.ended_at and inst.placements:
            start = min(p.started_at for p in inst.placements)
            lifespans.append((inst.ended_at - start).total_seconds() / 86400)
        elif inst.status == InstanceStatus.dead and inst.ended_at and inst.acquired_date:
            lifespans.append((inst.ended_at.date() - inst.acquired_date).days)

    # Latest "would buy again" opinion per instance
    latest_by_instance: dict[int, Assessment] = {}
    for a in sorted(assessments, key=lambda a: a.assessed_at):
        if a.would_buy_again:
            latest_by_instance[a.instance_id] = a
    buy_again: dict[str, int] = defaultdict(int)
    for a in latest_by_instance.values():
        buy_again[a.would_buy_again] += 1

    by_placement: dict[int, list[Assessment]] = defaultdict(list)
    for a in assessments:
        if a.placement_id:
            by_placement[a.placement_id].append(a)

    groups: dict[str, dict[str, dict[str, Any]]] = {
        "spot": {},
        "environment": {},
        "aspect": {},
        "sun_exposure": {},
    }
    now = utcnow()
    for inst in instances:
        for p in inst.placements:
            spot = p.spot
            if spot is None:
                continue
            keys = {
                "spot": (str(spot.id), f"{spot.area.name} › {spot.name}"),
                "environment": (spot.area.environment, spot.area.environment),
                "aspect": (spot.aspect or "unknown", spot.aspect or "unknown"),
                "sun_exposure": (spot.sun_exposure or "unknown", spot.sun_exposure or "unknown"),
            }
            days = ((p.ended_at or now) - p.started_at).total_seconds() / 86400
            died = p.end_event_id in death_event_ids
            for group, (key, label) in keys.items():
                g = groups[group].setdefault(
                    key, {"label": label, "placements": 0, "instances": set(), "deaths": 0, "ratings": [], "days": []}
                )
                g["placements"] += 1
                g["instances"].add(inst.id)
                g["deaths"] += int(died)
                g["ratings"].extend(a.overall for a in by_placement.get(p.id, []))
                g["days"].append(days)

    def perf(group: str) -> list[GroupPerformance]:
        out = [
            GroupPerformance(
                key=k,
                label=v["label"],
                placements=v["placements"],
                instances=len(v["instances"]),
                deaths=v["deaths"],
                avg_overall=_avg(v["ratings"]),
                avg_days=_avg(v["days"]),
            )
            for k, v in groups[group].items()
        ]
        return sorted(out, key=lambda g: (g.avg_overall is None, -(g.avg_overall or 0), g.deaths))

    end_reasons: dict[str, int] = defaultdict(int)
    for inst in instances:
        if inst.status != InstanceStatus.active and inst.end_reason:
            end_reasons[inst.end_reason.strip().lower()] += 1

    ratings = _rating_summary(assessments)
    return PlantInsights(
        plant_id=plant.id,
        instances_total=len(instances),
        status_counts=dict(status_counts),
        survival_rate=survival,
        avg_lifespan_days_dead=_avg(lifespans),
        ratings=ratings,
        would_buy_again=dict(buy_again),
        verdict=_verdict(dict(buy_again), ratings.avg_overall, survival, len(instances)),
        by_spot=perf("spot"),
        by_environment=perf("environment"),
        by_aspect=perf("aspect"),
        by_sun_exposure=perf("sun_exposure"),
        end_reasons=dict(end_reasons),
    )


def _verdict(buy_again: dict[str, int], avg_overall: float | None, survival: float | None, n: int) -> str:
    if n == 0:
        return "No instances yet"
    yes, no = buy_again.get("yes", 0), buy_again.get("no", 0)
    if yes > no and (avg_overall is None or avg_overall >= 3):
        return "Buy again"
    if no > yes or (avg_overall is not None and avg_overall < 2.5) or (survival is not None and survival < 0.34 and n >= 2):
        return "Avoid, or try a different location"
    if avg_overall is None and not buy_again:
        return "Not enough data - add an assessment"
    return "Mixed results"


def spot_insights(db: Session, spot: Spot) -> SpotInsights:
    placements = list(
        db.scalars(
            select(Placement)
            .where(Placement.spot_id == spot.id)
            .options(
                selectinload(Placement.instance).selectinload(PlantInstance.plant),
                selectinload(Placement.position),
            )
            .order_by(Placement.started_at.desc())
        )
    )
    pids = [p.id for p in placements]
    assessments = list(db.scalars(select(Assessment).where(Assessment.placement_id.in_(pids)))) if pids else []
    by_placement: dict[int, list[Assessment]] = defaultdict(list)
    for a in assessments:
        by_placement[a.placement_id].append(a)
    end_events = {
        e.id: e.event_type
        for e in db.scalars(
            select(InstanceEvent).where(InstanceEvent.id.in_([p.end_event_id for p in placements if p.end_event_id]))
        )
    }

    now = utcnow()
    history = []
    for p in placements:
        outcome = "current" if p.ended_at is None else end_events.get(p.end_event_id, "ended")
        history.append(
            SpotHistoryEntry(
                placement_id=p.id,
                instance_id=p.instance_id,
                plant_id=p.instance.plant_id,
                plant_name=p.instance.plant.common_name,
                plant_image_media_id=p.instance.plant.image_media_id,
                nickname=p.instance.nickname,
                position_label=p.position.label if p.position else None,
                started_at=p.started_at,
                ended_at=p.ended_at,
                days=round(((p.ended_at or now) - p.started_at).total_seconds() / 86400, 1),
                outcome=outcome,
                avg_overall=_avg([a.overall for a in by_placement.get(p.id, [])]),
            )
        )
    return SpotInsights(
        spot_id=spot.id,
        current_count=sum(1 for h in history if h.outcome == "current"),
        historic_count=sum(1 for h in history if h.outcome != "current"),
        deaths=sum(1 for h in history if h.outcome == EventType.died),
        avg_overall=_avg([a.overall for a in assessments]),
        history=history,
    )


def summary(db: Session) -> Summary:
    status_counts = dict(db.execute(select(PlantInstance.status, func.count()).group_by(PlantInstance.status)).all())

    def recent(stmt) -> list[RecentEvent]:
        rows = db.execute(stmt.limit(15)).all()
        return [
            RecentEvent(
                id=e.id,
                instance_id=e.instance_id,
                event_type=e.event_type,
                occurred_at=e.occurred_at,
                notes=e.notes,
                plant_name=plant_name,
                nickname=nickname,
            )
            for e, plant_name, nickname in rows
        ]

    base = (
        select(InstanceEvent, Plant.common_name, PlantInstance.nickname)
        .join(PlantInstance, PlantInstance.id == InstanceEvent.instance_id)
        .join(Plant, Plant.id == PlantInstance.plant_id)
        .order_by(InstanceEvent.occurred_at.desc(), InstanceEvent.id.desc())
    )
    losses = base.where(
        InstanceEvent.event_type.in_([EventType.died.value, EventType.removed.value])
    )

    last_assessed = (
        select(Assessment.instance_id, func.max(Assessment.assessed_at).label("last"))
        .group_by(Assessment.instance_id)
        .subquery()
    )
    cutoff = utcnow() - timedelta(days=ASSESS_STALE_DAYS)
    stale_rows = db.execute(
        select(PlantInstance.id, Plant.common_name, PlantInstance.nickname, last_assessed.c.last)
        .join(Plant, Plant.id == PlantInstance.plant_id)
        .outerjoin(last_assessed, last_assessed.c.instance_id == PlantInstance.id)
        .where(PlantInstance.status == InstanceStatus.active.value)
        .where((last_assessed.c.last.is_(None)) | (last_assessed.c.last < cutoff.replace(tzinfo=None)))
        .order_by(last_assessed.c.last.is_(None).desc(), last_assessed.c.last)
        .limit(20)
    ).all()

    return Summary(
        plants=db.scalar(select(func.count(Plant.id))) or 0,
        active_instances=status_counts.get(InstanceStatus.active.value, 0),
        areas=db.scalar(select(func.count(Area.id))) or 0,
        spots=db.scalar(select(func.count(Spot.id)).where(Spot.archived.is_(False))) or 0,
        status_counts=status_counts,
        recent_events=recent(base),
        recent_losses=recent(losses),
        needs_assessment=[
            NeedsAssessment(instance_id=i, plant_name=n, nickname=nick, last_assessed_at=last)
            for i, n, nick, last in stale_rows
        ],
    )
