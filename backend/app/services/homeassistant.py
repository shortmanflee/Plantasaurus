"""Home Assistant integration: discover labelled devices and watch assigned ones.

Devices are found by label through HA's template API (`POST /api/template`), which exposes
the device and label registries over plain REST. That needs a token from an admin user.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import utcnow
from app.models import Area, HAConfig, HADevice, Spot
from app.models.homeassistant import DeviceRole, device_problem

log = logging.getLogger("plantasaurus.homeassistant")

ROLES: tuple[DeviceRole, ...] = ("irrigation_zone", "plant_monitor")
ROLE_LABELS = {"irrigation_zone": "irrigation zone", "plant_monitor": "plant monitor"}
NOTIFICATION_ID = "plantasaurus_missing_devices"
SUPERVISOR_URL = "http://supervisor/core"

DEVICES_TEMPLATE = """
{%- set zones = label_devices(zone_label) -%}
{%- set monitors = label_devices(monitor_label) -%}
{%- set ns = namespace(devices=[]) -%}
{%- for d in (zones + monitors + check_ids) | unique -%}
  {%- if device_attr(d, 'id') -%}
    {%- set ns.devices = ns.devices + [{
      "id": d,
      "name": device_attr(d, 'name_by_user') or device_attr(d, 'name'),
      "area": area_name(d),
      "manufacturer": device_attr(d, 'manufacturer'),
      "model": device_attr(d, 'model'),
      "entities": device_entities(d)
    }] -%}
  {%- endif -%}
{%- endfor -%}
{{ {"zones": zones, "monitors": monitors, "devices": ns.devices} | tojson }}
"""


class HAError(Exception):
    pass


@dataclass
class Connection:
    url: str
    token: str
    source: Literal["settings", "environment", "supervisor"]


def get_config(db: Session) -> HAConfig:
    config = db.get(HAConfig, 1)
    if config is None:
        config = HAConfig(id=1)
        db.add(config)
        db.flush()
    return config


def resolve_connection(config: HAConfig) -> Connection | None:
    """UI settings win, then PLANTASAURUS_HA_URL/TOKEN, then the add-on supervisor token."""
    if config.url and config.token:
        return Connection(config.url.rstrip("/"), config.token, "settings")
    settings = get_settings()
    if settings.ha_url and settings.ha_token:
        return Connection(settings.ha_url.rstrip("/"), settings.ha_token, "environment")
    if supervisor_token := os.environ.get("SUPERVISOR_TOKEN"):
        return Connection(SUPERVISOR_URL, supervisor_token, "supervisor")
    return None


def _request(conn: Connection, method: str, path: str, body: dict[str, Any]) -> httpx.Response:
    try:
        resp = httpx.request(
            method,
            f"{conn.url}{path}",
            json=body,
            headers={"Authorization": f"Bearer {conn.token}"},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise HAError(f"Could not reach Home Assistant at {conn.url}: {exc}") from exc
    if resp.status_code == 401:
        raise HAError("Home Assistant rejected the access token")
    if resp.status_code == 403:
        raise HAError("The access token must belong to a Home Assistant administrator")
    if resp.status_code >= 400:
        raise HAError(f"Home Assistant returned {resp.status_code}: {resp.text[:200]}")
    return resp


def fetch_devices(conn: Connection, zone_label: str, monitor_label: str, check_ids: list[str]) -> dict[str, Any]:
    resp = _request(
        conn,
        "POST",
        "/api/template",
        {
            "template": DEVICES_TEMPLATE,
            "variables": {"zone_label": zone_label, "monitor_label": monitor_label, "check_ids": check_ids},
        },
    )
    try:
        data = json.loads(resp.text)
        assert isinstance(data, dict) and isinstance(data.get("devices"), list)
    except (ValueError, AssertionError) as exc:
        raise HAError("Unexpected response from Home Assistant's template API") from exc
    return data


def _assigned(db: Session) -> dict[DeviceRole, dict[str, list[int]]]:
    """role -> device_id -> spot ids."""
    out: dict[DeviceRole, dict[str, list[int]]] = {role: {} for role in ROLES}
    rows = db.execute(select(Spot.id, Spot.irrigation_zone_device_id, Spot.plant_monitor_device_id)).all()
    for spot_id, zone, monitor in rows:
        if zone:
            out["irrigation_zone"].setdefault(zone, []).append(spot_id)
        if monitor:
            out["plant_monitor"].setdefault(monitor, []).append(spot_id)
    return out


def sync(db: Session, *, notify: bool = True) -> HAConfig:
    """Refresh the device cache from HA and flag assigned devices that have gone.

    If HA can't be reached nothing is flagged: the error is recorded and raised as HAError.
    """
    config = get_config(db)
    conn = resolve_connection(config)
    if conn is None:
        raise HAError("Home Assistant is not configured")
    assigned = _assigned(db)
    assigned_ids = set(assigned["irrigation_zone"]) | set(assigned["plant_monitor"])
    try:
        data = fetch_devices(conn, config.irrigation_label, config.monitor_label, sorted(assigned_ids))
    except HAError as exc:
        config.last_sync_error = str(exc)
        db.commit()
        raise
    apply_snapshot(db, data, assigned)
    config.last_sync_at = utcnow()
    config.last_sync_error = None
    db.commit()
    if notify:
        notify_issues(db, config, conn)
    return config


def apply_snapshot(db: Session, data: dict[str, Any], assigned: dict[DeviceRole, dict[str, list[int]]]) -> None:
    now = utcnow()
    zones, monitors = set(data.get("zones") or []), set(data.get("monitors") or [])
    found = {d["id"]: d for d in data["devices"] if isinstance(d, dict) and d.get("id")}
    rows = {row.device_id: row for row in db.scalars(select(HADevice))}

    for device_id, info in found.items():
        row = rows.get(device_id)
        if row is None:
            row = rows[device_id] = HADevice(device_id=device_id)
            db.add(row)
        row.name = info.get("name")
        row.area_name = info.get("area")
        row.manufacturer = info.get("manufacturer")
        row.model = info.get("model")
        row.entities = [e for e in info.get("entities") or [] if isinstance(e, str)]
        row.exists_in_ha = True
        row.is_irrigation_zone = device_id in zones
        row.is_plant_monitor = device_id in monitors
        row.last_seen_at = now

    for device_id, row in rows.items():
        if device_id not in found:
            row.exists_in_ha = row.is_irrigation_zone = row.is_plant_monitor = False
        roles = [role for role in ROLES if device_id in assigned[role]]
        if not roles and not row.is_irrigation_zone and not row.is_plant_monitor:
            db.delete(row)  # neither labelled nor in use: forget it
            continue
        broken = any(device_problem(row, role) for role in roles)
        if broken and row.missing_since is None:
            row.missing_since = now
        elif not broken:
            row.missing_since = None


def list_issues(db: Session) -> list[dict[str, Any]]:
    spots = db.scalars(
        select(Spot)
        .where(
            Spot.archived.is_(False),
            or_(Spot.irrigation_zone_device_id.is_not(None), Spot.plant_monitor_device_id.is_not(None)),
        )
        .options(selectinload(Spot.area))
        .order_by(Spot.area_id, Spot.sort_order, Spot.name)
    )
    issues = []
    for spot in spots:
        for role, ref in (("irrigation_zone", spot.irrigation_zone), ("plant_monitor", spot.plant_monitor)):
            if ref and ref["problem"]:
                issues.append(
                    {
                        "spot_id": spot.id,
                        "spot_name": spot.name,
                        "area_id": spot.area_id,
                        "area_name": spot.area.name,
                        "role": role,
                        "device_id": ref["device_id"],
                        "device_name": ref["name"],
                        "problem": ref["problem"],
                        "missing_since": ref["missing_since"],
                    }
                )
    return issues


def notify_issues(db: Session, config: HAConfig, conn: Connection) -> None:
    """Mirror the current issues into an HA persistent notification (only when they change)."""
    issues = list_issues(db) if config.notify_in_ha else []
    fingerprint = hashlib.sha1(
        json.dumps(sorted((i["spot_id"], i["role"], i["device_id"], i["problem"]) for i in issues)).encode()
    ).hexdigest()
    if fingerprint == config.last_notified:
        return
    try:
        if issues:
            lines = [
                f"- **{i['area_name']} → {i['spot_name']}**: {ROLE_LABELS[i['role']]} "
                f"“{i['device_name'] or i['device_id']}” "
                + ("was removed from Home Assistant" if i["problem"] == "deleted" else "no longer has its label")
                for i in issues
            ]
            _request(
                conn,
                "POST",
                "/api/services/persistent_notification/create",
                {
                    "notification_id": NOTIFICATION_ID,
                    "title": "Plantasaurus: spot devices need updating",
                    "message": "\n".join(lines) + "\n\nReassign or remove them on each spot in Plantasaurus.",
                },
            )
        elif config.last_notified is not None:
            _request(conn, "POST", "/api/services/persistent_notification/dismiss", {"notification_id": NOTIFICATION_ID})
    except HAError as exc:
        log.warning("Could not update Home Assistant notification: %s", exc)
        return
    config.last_notified = fingerprint if issues else None
    db.commit()


def validate_assignment(db: Session, spot: Spot | None, role: DeviceRole, device_id: str | None) -> None:
    """Check a device id being set on a spot is a current, correctly-labelled HA device."""
    if device_id is None:
        return
    current = getattr(spot, f"{role}_device_id") if spot else None
    if device_id == current:
        return  # unchanged; don't block unrelated edits while a device is missing
    device = db.get(HADevice, device_id)
    if device_problem(device, role):
        try:
            sync(db, notify=False)  # maybe it was added in HA since the last sync
        except HAError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        device = db.get(HADevice, device_id)
        if device_problem(device, role):
            config = get_config(db)
            label = config.irrigation_label if role == "irrigation_zone" else config.monitor_label
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Device {device_id} is not a Home Assistant device labelled '{label}'",
            )
    if role == "plant_monitor":
        other = db.scalar(
            select(Spot).where(Spot.plant_monitor_device_id == device_id, Spot.id != (spot.id if spot else -1))
        )
        if other is not None:
            area = db.get(Area, other.area_id)
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"That plant monitor is already assigned to {area.name if area else ''} → {other.name}",
            )


def run_background_sync() -> None:
    """One scheduled sync tick, with its own session. Quietly skips when HA isn't set up."""
    from app.db import new_session

    with new_session() as db:
        if resolve_connection(get_config(db)) is None:
            return
        try:
            sync(db)
        except HAError as exc:
            log.warning("Home Assistant sync failed: %s", exc)
