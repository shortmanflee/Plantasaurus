"""The Plantasaurus MCP server: tools for every resource in the REST API."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AuthProvider
from fastmcp.utilities.types import Image
from pydantic import Field

from app import __version__
from app.mcp_server.backend import Backend
from app.models.enums import SYSTEM_EVENT_TYPES, CustomFieldEntity, Environment, EventType, InstanceStatus
from app.schemas.custom_field import CustomFieldCreate, CustomFieldUpdate
from app.schemas.instance import (
    AssessmentUpdate,
    AssessRequest,
    EventUpdate,
    InstanceCreate,
    InstanceUpdate,
    MoveRequest,
    PropagateRequest,
    RepotRequest,
    RetireRequest,
    ReviveRequest,
    TransplantRequest,
)
from app.schemas.location import AreaCreate, AreaUpdate, PositionCreate, PositionUpdate, SpotCreate, SpotUpdate
from app.schemas.media import MediaUpdate
from app.schemas.plant import PlantCreate, PlantUpdate
from app.schemas.user import UserCreate, UserUpdate

INSTRUCTIONS = """\
Plantasaurus tracks the plants in a house and garden.

Concepts:
- Plant: a master entry for a species/cultivar (e.g. Monstera deliciosa), optionally imported from Open Plantbook.
- Instance ("my plants"): one physical plant (or a group of identical ones). Belongs to a Plant and has a history.
- Location hierarchy: Area (indoor/outdoor/greenhouse/covered) → Spot (with traits like aspect, sun) → Position (optional).
- Placement: a period an instance spent in a spot/position. Managed automatically by the instance action tools.
- Event: append-only timeline entry. Lifecycle events (planted, moved, transplanted, repotted, died, removed,
  given_away, revived, propagated, assessment) only come from instance actions and cannot be deleted.
  Care/observation events (watered, fed, pruned, pest_disease, treated, flowered, fruited, harvested, note, photo)
  are logged with log_event and can be edited or deleted.
- Assessment: 1-5 ratings plus "would buy again?" and "good location?", tied to the placement at the time.

Tips:
- Use get_location_tree to see every area, spot, position and what currently lives there.
- To move, transplant, repot, retire, revive or propagate a plant use the instance action tools, never update_instance.
- Prefer retire_instance over delete_instance: deleting destroys history and insights.
- Times are ISO 8601; omit them to mean "now". Times cannot be in the future.
- Custom fields (list_custom_fields) define extra keys allowed in the `attributes` of plants, instances, areas and spots.
- Backups (admin): create_backup saves everything to a zip on the server; restore_backup replaces ALL data
  with a backup (a safety backup of the current data is taken first). Only restore when explicitly asked.
"""

READ = {"readOnlyHint": True, "openWorldHint": False}
CREATE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}
UPDATE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
DELETE = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False}

CareEventType = Literal[tuple(t.value for t in EventType if t not in SYSTEM_EVENT_TYPES)]  # type: ignore[valid-type]

Limit = Annotated[int, Field(ge=1, le=500, description="Page size")]
Offset = Annotated[int, Field(ge=0, description="Items to skip")]
Force = Annotated[bool, Field(description="Delete even if placement history exists (history is lost)")]

_IMAGE_SIGNATURES = {
    b"\x89PNG": ("png", "image/png"),
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
    b"GIF8": ("gif", "image/gif"),
    b"RIFF": ("webp", "image/webp"),
}


def _dump(model, *, partial: bool = False) -> dict[str, Any]:
    """Serialise a request model. For updates only send the fields the caller provided."""
    return model.model_dump(mode="json", exclude_unset=partial)


def _require_changes(changes) -> dict[str, Any]:
    body = _dump(changes, partial=True)
    if not body:
        raise ToolError("No changes given")
    return body


def build_server(backend: Backend, *, auth: AuthProvider | None = None) -> FastMCP:
    mcp = FastMCP(
        "Plantasaurus",
        instructions=INSTRUCTIONS,
        version=__version__,
        auth=auth,
        mask_error_details=True,
    )
    api = backend

    # ---- Overview -----------------------------------------------------------

    @mcp.tool(annotations=READ, tags={"overview"})
    async def whoami() -> dict:
        """The Plantasaurus user the MCP connection is authenticated as."""
        return await api.get("/auth/me")

    @mcp.tool(annotations=READ, tags={"overview", "insights"})
    async def get_summary() -> dict:
        """Dashboard summary: counts, survival rates, recent activity and best/worst performers."""
        return await api.get("/insights/summary")

    # ---- Plants -------------------------------------------------------------

    @mcp.tool(annotations=READ, tags={"plants"})
    async def list_plants(
        q: Annotated[str | None, Field(description="Search common, scientific or cultivar name")] = None,
        category: str | None = None,
        sort: Literal["name", "-created_at", "created_at"] = "name",
        limit: Limit = 50,
        offset: Offset = 0,
    ) -> dict:
        """List plant species/cultivars, with active and total instance counts."""
        return await api.get("/plants", q=q, category=category, sort=sort, limit=limit, offset=offset)

    @mcp.tool(annotations=READ, tags={"plants"})
    async def list_plant_categories() -> list[str]:
        """The distinct plant categories in use."""
        return await api.get("/plants/categories")

    @mcp.tool(annotations=READ, tags={"plants"})
    async def get_plant(plant_id: int) -> dict:
        """Get one plant, including its care ranges."""
        return await api.get(f"/plants/{plant_id}")

    @mcp.tool(annotations=CREATE, tags={"plants"})
    async def create_plant(plant: PlantCreate) -> dict:
        """Add a plant species/cultivar manually. To use Open Plantbook data, use import_plant_from_openplantbook."""
        return await api.post("/plants", _dump(plant))

    @mcp.tool(annotations=UPDATE, tags={"plants"})
    async def update_plant(plant_id: int, changes: PlantUpdate) -> dict:
        """Change a plant. Only the fields given are changed; pass null to clear a field."""
        return await api.patch(f"/plants/{plant_id}", _require_changes(changes))

    @mcp.tool(annotations=DELETE, tags={"plants"})
    async def delete_plant(plant_id: int) -> str:
        """Delete a plant. Refused while it has instances (delete or reassign those first)."""
        await api.delete(f"/plants/{plant_id}")
        return f"Deleted plant {plant_id}"

    @mcp.tool(annotations=READ, tags={"plants", "instances"})
    async def list_plant_instances(plant_id: int) -> list[dict]:
        """Every instance (past and present) of a plant."""
        return await api.get(f"/plants/{plant_id}/instances")

    @mcp.tool(annotations=READ, tags={"plants", "insights"})
    async def get_plant_insights(plant_id: int) -> dict:
        """How a plant has fared: survival rate, lifespan, ratings, buy-again verdict, broken down by location."""
        return await api.get(f"/plants/{plant_id}/insights")

    # ---- Open Plantbook -----------------------------------------------------

    OPEN_WORLD_READ = {**READ, "openWorldHint": True}

    @mcp.tool(annotations=READ, tags={"openplantbook"})
    async def get_openplantbook_status() -> dict:
        """Whether Open Plantbook credentials are configured."""
        return await api.get("/openplantbook/status")

    @mcp.tool(annotations=OPEN_WORLD_READ, tags={"openplantbook"})
    async def search_openplantbook(
        q: Annotated[str, Field(min_length=2, description="Common or scientific name")],
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> list[dict]:
        """Search Open Plantbook. Results show `already_imported_plant_id` when the plant is already in Plantasaurus."""
        return await api.get("/openplantbook/search", q=q, limit=limit)

    @mcp.tool(annotations=OPEN_WORLD_READ, tags={"openplantbook"})
    async def get_openplantbook_plant(pid: Annotated[str, Field(description="Open Plantbook pid")]) -> dict:
        """Full Open Plantbook record (care ranges, image URL) without importing it."""
        return await api.get(f"/openplantbook/plants/{pid}")

    @mcp.tool(annotations={**CREATE, "openWorldHint": True}, tags={"openplantbook", "plants"})
    async def import_plant_from_openplantbook(
        pid: Annotated[str, Field(description="Open Plantbook pid, from search_openplantbook")],
        common_name: Annotated[str | None, Field(description="Override the display name")] = None,
        download_image: bool = True,
    ) -> dict:
        """Create a plant from Open Plantbook, including care ranges and (optionally) its image."""
        return await api.post(
            "/plants/import-opb", {"pid": pid, "common_name": common_name, "download_image": download_image}
        )

    @mcp.tool(annotations={**UPDATE, "openWorldHint": True}, tags={"openplantbook", "plants"})
    async def refresh_plant_from_openplantbook(plant_id: int, refresh_image: bool = False) -> dict:
        """Re-fetch care ranges from Open Plantbook for an imported plant. Names and notes are kept."""
        return await api.post(f"/plants/{plant_id}/opb-refresh", refresh_image=refresh_image)

    # ---- Locations ----------------------------------------------------------

    @mcp.tool(annotations=READ, tags={"locations"})
    async def get_location_tree(include_archived: bool = False) -> list[dict]:
        """The full Area → Spot → Position tree, with the plants currently in each."""
        return await api.get("/locations/tree", include_archived=include_archived)

    @mcp.tool(annotations=READ, tags={"locations"})
    async def list_areas(environment: Environment | None = None) -> list[dict]:
        """List areas (e.g. Living Room, Back Garden)."""
        return await api.get("/areas", environment=environment)

    @mcp.tool(annotations=READ, tags={"locations"})
    async def get_area(area_id: int) -> dict:
        """Get one area."""
        return await api.get(f"/areas/{area_id}")

    @mcp.tool(annotations=CREATE, tags={"locations"})
    async def create_area(area: AreaCreate) -> dict:
        """Create an area. Names must be unique."""
        return await api.post("/areas", _dump(area))

    @mcp.tool(annotations=UPDATE, tags={"locations"})
    async def update_area(area_id: int, changes: AreaUpdate) -> dict:
        """Change an area. Only the fields given are changed."""
        return await api.patch(f"/areas/{area_id}", _require_changes(changes))

    @mcp.tool(annotations=DELETE, tags={"locations"})
    async def delete_area(area_id: int, force: Force = False) -> str:
        """Delete an area and its spots. Refused while plants live there, or if it has history unless force=true."""
        await api.delete(f"/areas/{area_id}", force=force)
        return f"Deleted area {area_id}"

    @mcp.tool(annotations=READ, tags={"locations"})
    async def list_spots(
        area_id: int | None = None,
        include_archived: bool = False,
        q: Annotated[str | None, Field(description="Search by name")] = None,
    ) -> list[dict]:
        """List spots (e.g. Windowsill, Flowerbed) with their traits and Home Assistant devices."""
        return await api.get("/spots", area_id=area_id, include_archived=include_archived, q=q)

    @mcp.tool(annotations=READ, tags={"locations"})
    async def get_spot(spot_id: int) -> dict:
        """Get one spot."""
        return await api.get(f"/spots/{spot_id}")

    @mcp.tool(annotations=CREATE, tags={"locations"})
    async def create_spot(spot: SpotCreate) -> dict:
        """Create a spot in an area. Set position_count to auto-create positions labelled 1..N."""
        return await api.post("/spots", _dump(spot))

    @mcp.tool(annotations=UPDATE, tags={"locations"})
    async def update_spot(spot_id: int, changes: SpotUpdate) -> dict:
        """Change a spot. Only the fields given are changed. Set archived=true to retire a spot but keep its history."""
        return await api.patch(f"/spots/{spot_id}", _require_changes(changes))

    @mcp.tool(annotations=DELETE, tags={"locations"})
    async def delete_spot(spot_id: int, force: Force = False) -> str:
        """Delete a spot. Refused while occupied, or if it has history unless force=true (prefer archiving)."""
        await api.delete(f"/spots/{spot_id}", force=force)
        return f"Deleted spot {spot_id}"

    @mcp.tool(annotations=READ, tags={"locations", "insights"})
    async def get_spot_insights(spot_id: int) -> dict:
        """What has grown in a spot and how well it did."""
        return await api.get(f"/spots/{spot_id}/insights")

    @mcp.tool(annotations=READ, tags={"locations"})
    async def list_positions(spot_id: int | None = None) -> list[dict]:
        """List positions, optionally within one spot."""
        return await api.get("/positions", spot_id=spot_id)

    @mcp.tool(annotations=READ, tags={"locations"})
    async def get_position(position_id: int) -> dict:
        """Get one position."""
        return await api.get(f"/positions/{position_id}")

    @mcp.tool(annotations=CREATE, tags={"locations"})
    async def create_position(position: PositionCreate) -> dict:
        """Add a position to a spot. Labels must be unique within the spot."""
        return await api.post("/positions", _dump(position))

    @mcp.tool(annotations=UPDATE, tags={"locations"})
    async def update_position(position_id: int, changes: PositionUpdate) -> dict:
        """Change a position's label, order or notes."""
        return await api.patch(f"/positions/{position_id}", _require_changes(changes))

    @mcp.tool(annotations=DELETE, tags={"locations"})
    async def delete_position(position_id: int, force: Force = False) -> str:
        """Delete a position. Refused while occupied, or if it has history unless force=true."""
        await api.delete(f"/positions/{position_id}", force=force)
        return f"Deleted position {position_id}"

    # ---- Instances ----------------------------------------------------------

    @mcp.tool(annotations=READ, tags={"instances"})
    async def list_instances(
        status: Annotated[list[InstanceStatus] | None, Field(description="Default: all statuses")] = None,
        plant_id: int | None = None,
        area_id: int | None = None,
        spot_id: int | None = None,
        q: Annotated[str | None, Field(description="Search plant name or nickname")] = None,
        sort: Literal["plant", "-created_at", "acquired_date", "-acquired_date"] = "plant",
        limit: Limit = 100,
        offset: Offset = 0,
    ) -> dict:
        """List the user's plants (instances) with their current location and latest rating."""
        return await api.get(
            "/instances",
            status=[s.value for s in status or []],
            plant_id=plant_id,
            area_id=area_id,
            spot_id=spot_id,
            q=q,
            sort=sort,
            limit=limit,
            offset=offset,
        )

    @mcp.tool(annotations=READ, tags={"instances"})
    async def get_instance(instance_id: int) -> dict:
        """Get one instance, including every placement it has had and its propagated children."""
        return await api.get(f"/instances/{instance_id}")

    @mcp.tool(annotations=READ, tags={"instances", "events"})
    async def get_instance_timeline(instance_id: int) -> list[dict]:
        """An instance's events (newest first) with their assessments and photos."""
        return await api.get(f"/instances/{instance_id}/timeline")

    @mcp.tool(annotations=CREATE, tags={"instances"})
    async def create_instance(instance: InstanceCreate) -> dict:
        """Add a plant the user owns. Give spot_id and/or position_id to place it (records 'planted'),
        otherwise it is recorded as 'acquired' and unplaced."""
        return await api.post("/instances", _dump(instance))

    @mcp.tool(annotations=UPDATE, tags={"instances"})
    async def update_instance(instance_id: int, changes: InstanceUpdate) -> dict:
        """Edit descriptive fields (nickname, quantity, source, cost, notes, attributes…).
        Use the action tools to change location or status."""
        return await api.patch(f"/instances/{instance_id}", _require_changes(changes))

    @mcp.tool(annotations=DELETE, tags={"instances"})
    async def delete_instance(instance_id: int) -> str:
        """Permanently delete an instance and all its history and photos. Prefer retire_instance."""
        await api.delete(f"/instances/{instance_id}")
        return f"Deleted instance {instance_id}"

    @mcp.tool(annotations=CREATE, tags={"instances", "actions"})
    async def move_instance(instance_id: int, move: MoveRequest) -> dict:
        """Move an active plant to another spot/position. Closes the current placement and opens a new one."""
        return await api.post(f"/instances/{instance_id}/move", _dump(move))

    @mcp.tool(annotations=CREATE, tags={"instances", "actions"})
    async def transplant_instance(instance_id: int, transplant: TransplantRequest) -> dict:
        """Move a plant into new ground or a new container, recording pot size and soil."""
        return await api.post(f"/instances/{instance_id}/transplant", _dump(transplant))

    @mcp.tool(annotations=CREATE, tags={"instances", "actions"})
    async def repot_instance(instance_id: int, repot: RepotRequest) -> dict:
        """Repot a plant without changing its location."""
        return await api.post(f"/instances/{instance_id}/repot", _dump(repot))

    @mcp.tool(annotations=CREATE, tags={"instances", "actions"})
    async def retire_instance(instance_id: int, retire: RetireRequest) -> dict:
        """Record that a plant died, was removed or was given away, with an optional reason and final assessment."""
        return await api.post(f"/instances/{instance_id}/retire", _dump(retire))

    @mcp.tool(annotations=CREATE, tags={"instances", "actions"})
    async def revive_instance(instance_id: int, revive: ReviveRequest) -> dict:
        """Bring a retired plant back to active, optionally placing it."""
        return await api.post(f"/instances/{instance_id}/revive", _dump(revive))

    @mcp.tool(annotations=CREATE, tags={"instances", "actions"})
    async def propagate_instance(instance_id: int, propagate: PropagateRequest) -> dict:
        """Create a new instance from a cutting, division or seed of this one. Returns the new instance."""
        return await api.post(f"/instances/{instance_id}/propagate", _dump(propagate))

    @mcp.tool(annotations=CREATE, tags={"instances", "assessments"})
    async def assess_instance(instance_id: int, assessment: AssessRequest) -> dict:
        """Record how well a plant is doing (1-5 ratings, would buy again, good location)."""
        return await api.post(f"/instances/{instance_id}/assess", _dump(assessment))

    # ---- Events -------------------------------------------------------------

    @mcp.tool(annotations=READ, tags={"events"})
    async def list_events(
        instance_id: int | None = None,
        event_type: list[EventType] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: Limit = 100,
        offset: Offset = 0,
    ) -> dict:
        """List timeline events across all plants, newest first."""
        return await api.get(
            "/events",
            instance_id=instance_id,
            event_type=[t.value for t in event_type or []],
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )

    @mcp.tool(annotations=READ, tags={"events"})
    async def get_event(event_id: int) -> dict:
        """Get one event."""
        return await api.get(f"/events/{event_id}")

    @mcp.tool(annotations=CREATE, tags={"events"})
    async def log_event(
        instance_id: int,
        event_type: CareEventType,
        occurred_at: Annotated[datetime | None, Field(description="Defaults to now")] = None,
        notes: str | None = None,
        data: Annotated[dict[str, Any] | None, Field(description="Free-form details, e.g. {'fertiliser': 'tomato feed'}")] = None,
    ) -> dict:
        """Log a care or observation event (watered, fed, pruned, pest_disease, treated, flowered, fruited,
        harvested, photo, note) on a plant's timeline."""
        body = {
            "instance_id": instance_id,
            "event_type": event_type,
            "occurred_at": occurred_at.isoformat() if occurred_at else None,
            "notes": notes,
            "data": data or {},
        }
        return await api.post("/events", body)

    @mcp.tool(annotations=UPDATE, tags={"events"})
    async def update_event(event_id: int, changes: EventUpdate) -> dict:
        """Edit an event. Lifecycle and assessment events only allow notes to change."""
        return await api.patch(f"/events/{event_id}", _require_changes(changes))

    @mcp.tool(annotations=DELETE, tags={"events"})
    async def delete_event(event_id: int) -> str:
        """Delete a care/observation event. Lifecycle events cannot be deleted."""
        await api.delete(f"/events/{event_id}")
        return f"Deleted event {event_id}"

    # ---- Assessments --------------------------------------------------------

    @mcp.tool(annotations=READ, tags={"assessments"})
    async def list_assessments(
        instance_id: int | None = None,
        plant_id: int | None = None,
        spot_id: int | None = None,
        limit: Limit = 100,
        offset: Offset = 0,
    ) -> dict:
        """List assessments, newest first. Create new ones with assess_instance."""
        return await api.get(
            "/assessments", instance_id=instance_id, plant_id=plant_id, spot_id=spot_id, limit=limit, offset=offset
        )

    @mcp.tool(annotations=READ, tags={"assessments"})
    async def get_assessment(assessment_id: int) -> dict:
        """Get one assessment."""
        return await api.get(f"/assessments/{assessment_id}")

    @mcp.tool(annotations=UPDATE, tags={"assessments"})
    async def update_assessment(assessment_id: int, changes: AssessmentUpdate) -> dict:
        """Change an assessment's ratings, notes or time. Only the fields given are changed."""
        return await api.patch(f"/assessments/{assessment_id}", _require_changes(changes))

    @mcp.tool(annotations=DELETE, tags={"assessments"})
    async def delete_assessment(assessment_id: int) -> str:
        """Delete an assessment and its timeline event."""
        await api.delete(f"/assessments/{assessment_id}")
        return f"Deleted assessment {assessment_id}"

    # ---- Media --------------------------------------------------------------

    @mcp.tool(annotations=READ, tags={"media"})
    async def list_media(
        plant_id: int | None = None,
        instance_id: int | None = None,
        event_id: int | None = None,
        limit: Limit = 100,
        offset: Offset = 0,
    ) -> dict:
        """List photo records (metadata only; use view_media to see an image)."""
        return await api.get(
            "/media", plant_id=plant_id, instance_id=instance_id, event_id=event_id, limit=limit, offset=offset
        )

    @mcp.tool(annotations=READ, tags={"media"})
    async def get_media(media_id: int) -> dict:
        """Get a photo's metadata."""
        return await api.get(f"/media/{media_id}")

    @mcp.tool(annotations=READ, tags={"media"})
    async def view_media(
        media_id: int,
        full_size: Annotated[bool, Field(description="Original instead of a 400px thumbnail")] = False,
    ) -> Image:
        """Look at a photo."""
        response = await api.send("GET", f"/media/{media_id}/{'file' if full_size else 'thumb'}")
        mime = response.headers.get("content-type", "image/jpeg").split(";")[0]
        return Image(data=response.content, format=mime.removeprefix("image/"))

    @mcp.tool(annotations=CREATE, tags={"media"})
    async def upload_media(
        image_base64: Annotated[str, Field(description="The image file (JPEG, PNG, WebP, GIF), base64-encoded")],
        caption: str | None = None,
        taken_at: datetime | None = None,
        plant_id: Annotated[int | None, Field(description="Attach to a plant (e.g. as a reference photo)")] = None,
        instance_id: Annotated[int | None, Field(description="Attach to one of the user's plants")] = None,
        event_id: Annotated[int | None, Field(description="Attach to a timeline event")] = None,
        log_photo_event: Annotated[
            bool, Field(description="With instance_id: also add a 'photo' event to the timeline")
        ] = False,
    ) -> dict:
        """Upload a photo. Large images are resized and a thumbnail is made automatically."""
        try:
            content = base64.b64decode(image_base64.split(",", 1)[-1], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ToolError("image_base64 is not valid base64") from exc
        ext, mime = next(
            (v for sig, v in _IMAGE_SIGNATURES.items() if content.startswith(sig)), ("bin", "application/octet-stream")
        )
        return await api.call(
            "POST",
            "/media",
            files={"file": (f"upload.{ext}", content, mime)},
            data={
                "caption": caption,
                "taken_at": taken_at,
                "plant_id": plant_id,
                "instance_id": instance_id,
                "event_id": event_id,
                "log_photo_event": log_photo_event,
            },
        )

    @mcp.tool(annotations=UPDATE, tags={"media"})
    async def update_media(media_id: int, changes: MediaUpdate) -> dict:
        """Change a photo's caption, time or what it is attached to."""
        return await api.patch(f"/media/{media_id}", _require_changes(changes))

    @mcp.tool(annotations=DELETE, tags={"media"})
    async def delete_media(media_id: int) -> str:
        """Delete a photo and its files."""
        await api.delete(f"/media/{media_id}")
        return f"Deleted media {media_id}"

    # ---- Custom fields ------------------------------------------------------

    @mcp.tool(annotations=READ, tags={"custom fields"})
    async def list_custom_fields(entity: CustomFieldEntity | None = None) -> list[dict]:
        """Custom field definitions: the extra `attributes` keys allowed on plants, instances, areas and spots."""
        return await api.get("/custom-fields", entity=entity)

    @mcp.tool(annotations=READ, tags={"custom fields"})
    async def get_custom_field(field_id: int) -> dict:
        """Get one custom field definition."""
        return await api.get(f"/custom-fields/{field_id}")

    @mcp.tool(annotations=CREATE, tags={"custom fields", "admin"})
    async def create_custom_field(field: CustomFieldCreate) -> dict:
        """Define a custom field (admin only). Select fields need options."""
        return await api.post("/custom-fields", _dump(field))

    @mcp.tool(annotations=UPDATE, tags={"custom fields", "admin"})
    async def update_custom_field(field_id: int, changes: CustomFieldUpdate) -> dict:
        """Change a custom field's label, options, help text or order (admin only)."""
        return await api.patch(f"/custom-fields/{field_id}", _require_changes(changes))

    @mcp.tool(annotations=DELETE, tags={"custom fields", "admin"})
    async def delete_custom_field(field_id: int) -> str:
        """Delete a custom field definition (admin only). Stored values are kept but hidden."""
        await api.delete(f"/custom-fields/{field_id}")
        return f"Deleted custom field {field_id}"

    # ---- Users and tokens ---------------------------------------------------

    @mcp.tool(annotations=READ, tags={"users"})
    async def list_users() -> list[dict]:
        """List user accounts."""
        return await api.get("/users")

    @mcp.tool(annotations=READ, tags={"users"})
    async def get_user(user_id: int) -> dict:
        """Get one user account."""
        return await api.get(f"/users/{user_id}")

    @mcp.tool(annotations=CREATE, tags={"users", "admin"})
    async def create_user(user: UserCreate) -> dict:
        """Create a user account (admin only)."""
        return await api.post("/users", _dump(user))

    @mcp.tool(annotations=UPDATE, tags={"users"})
    async def update_user(user_id: int, changes: UserUpdate) -> dict:
        """Change a user. Non-admins can only edit themselves and cannot change roles or activation."""
        return await api.patch(f"/users/{user_id}", _require_changes(changes))

    @mcp.tool(annotations=DELETE, tags={"users", "admin"})
    async def delete_user(user_id: int) -> str:
        """Delete a user account (admin only). You cannot delete yourself."""
        await api.delete(f"/users/{user_id}")
        return f"Deleted user {user_id}"

    @mcp.tool(annotations=READ, tags={"tokens"})
    async def list_api_tokens() -> list[dict]:
        """List API tokens (your own; admins see all). Secrets are never shown."""
        return await api.get("/tokens")

    @mcp.tool(annotations=CREATE, tags={"tokens"})
    async def create_api_token(name: Annotated[str, Field(min_length=1, max_length=128)]) -> dict:
        """Create an API token for an integration. The full token is returned only once."""
        return await api.post("/tokens", {"name": name})

    @mcp.tool(annotations=DELETE, tags={"tokens"})
    async def revoke_api_token(token_id: int) -> str:
        """Revoke an API token. Revoking the token this MCP connection uses will end its access."""
        await api.delete(f"/tokens/{token_id}")
        return f"Revoked API token {token_id}"

    # ---- Backups ------------------------------------------------------------

    @mcp.tool(annotations=READ, tags={"backups", "admin"})
    async def list_backups() -> list[dict]:
        """List backups on the server, newest first, with their status and what they contain (admin only)."""
        return await api.get("/backups")

    @mcp.tool(annotations=READ, tags={"backups", "admin"})
    async def get_backup(backup_id: int) -> dict:
        """Get one backup's status, size and row counts (admin only)."""
        return await api.get(f"/backups/{backup_id}")

    @mcp.tool(annotations=CREATE, tags={"backups", "admin"})
    async def create_backup() -> dict:
        """Back up every plant, instance, location, placement, event, assessment, custom field and photo
        to a zip on the server (admin only). Waits until it is finished and returns it; check `status`
        is "ready". Users, API tokens and integration credentials are not included. The zip can be
        downloaded from Settings → Backups or GET /api/v1/backups/{id}/download."""
        return await api.post("/backups", wait=True)

    @mcp.tool(annotations={**DELETE, "idempotentHint": False}, tags={"backups", "admin"})
    async def restore_backup(backup_id: int) -> dict:
        """Replace ALL plant data and photos with the contents of a backup on the server (admin only).
        Only do this when the user has clearly asked for it. The current data is backed up first; the
        result's `safety_backup_id` is that backup, so restoring it undoes this. Users, API tokens and
        integration settings are not changed."""
        return await api.post(f"/backups/{backup_id}/restore")

    @mcp.tool(annotations=DELETE, tags={"backups", "admin"})
    async def delete_backup(backup_id: int) -> str:
        """Delete a backup zip from the server (admin only)."""
        await api.delete(f"/backups/{backup_id}")
        return f"Deleted backup {backup_id}"

    # ---- Home Assistant -----------------------------------------------------

    @mcp.tool(annotations=READ, tags={"homeassistant"})
    async def get_homeassistant_status() -> dict:
        """Home Assistant connection status, labels in use, last sync and number of device issues."""
        return await api.get("/homeassistant/status")

    @mcp.tool(annotations={**READ, "openWorldHint": True}, tags={"homeassistant"})
    async def list_homeassistant_devices(
        role: Literal["irrigation_zone", "plant_monitor"], refresh: bool = True
    ) -> list[dict]:
        """HA devices labelled as irrigation zones or plant monitors, with the spots they are assigned to.
        Assign one to a spot with update_spot (irrigation_zone_device_id / plant_monitor_device_id)."""
        return await api.get("/homeassistant/devices", role=role, refresh=refresh)

    @mcp.tool(annotations=READ, tags={"homeassistant"})
    async def list_homeassistant_issues() -> list[dict]:
        """Spots whose assigned HA device has been deleted or lost its label."""
        return await api.get("/homeassistant/issues")

    @mcp.tool(annotations={**UPDATE, "openWorldHint": True}, tags={"homeassistant"})
    async def sync_homeassistant() -> dict:
        """Re-read devices from Home Assistant now and re-check the assigned ones."""
        return await api.post("/homeassistant/sync")

    return mcp
