from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.auth.deps import DB, AdminUser, CurrentUser
from app.config import get_settings
from app.models import HADevice
from app.models.homeassistant import DeviceRole
from app.schemas.homeassistant import HAConfigUpdate, HADeviceRead, HAIssue, HAStatus
from app.services import homeassistant as ha

router = APIRouter(prefix="/homeassistant", tags=["home assistant"])


def _status(db) -> HAStatus:
    config = ha.get_config(db)
    conn = ha.resolve_connection(config)
    return HAStatus(
        configured=conn is not None,
        source=conn.source if conn else None,
        url=conn.url if conn else config.url,
        token_set=bool(conn and conn.token),
        irrigation_label=config.irrigation_label,
        monitor_label=config.monitor_label,
        notify_in_ha=config.notify_in_ha,
        sync_interval_seconds=get_settings().ha_sync_interval_seconds,
        last_sync_at=config.last_sync_at,
        last_sync_error=config.last_sync_error,
        issue_count=len(ha.list_issues(db)),
    )


def _sync_or_502(db) -> None:
    try:
        ha.sync(db)
    except ha.HAError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.get("/status", response_model=HAStatus)
def get_status(db: DB, _: CurrentUser) -> HAStatus:
    return _status(db)


@router.put(
    "/config",
    response_model=HAStatus,
    summary="Save the HA connection. It is tested first and only saved if HA answers.",
)
def update_config(payload: HAConfigUpdate, db: DB, _: AdminUser) -> HAStatus:
    config = ha.get_config(db)
    url = (payload.url or "").strip().rstrip("/") or None
    token = payload.token.strip() if payload.token else config.token
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "URL must start with http:// or https://")
    if url and not token:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "An access token is required")

    config.url, config.token = (url, token) if url else (None, None)
    config.irrigation_label = payload.irrigation_label.strip()
    config.monitor_label = payload.monitor_label.strip()
    config.notify_in_ha = payload.notify_in_ha
    conn = ha.resolve_connection(config)
    if conn is not None:
        try:
            ha.fetch_devices(conn, config.irrigation_label, config.monitor_label, [])
        except ha.HAError as exc:
            db.rollback()
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if conn is None:
        config.last_notified = None
    db.commit()
    if conn is not None:
        _sync_or_502(db)
    return _status(db)


@router.post("/sync", response_model=HAStatus, summary="Re-read devices from HA now and re-check assigned ones")
def sync_now(db: DB, _: CurrentUser) -> HAStatus:
    _sync_or_502(db)
    return _status(db)


@router.get(
    "/devices",
    response_model=list[HADeviceRead],
    summary="HA devices carrying the irrigation-zone or plant-monitor label, for assigning to spots",
)
def list_devices(db: DB, _: CurrentUser, role: DeviceRole, refresh: bool = True) -> list[HADeviceRead]:
    if refresh:
        _sync_or_502(db)
    flag = HADevice.is_irrigation_zone if role == "irrigation_zone" else HADevice.is_plant_monitor
    devices = list(db.scalars(select(HADevice).where(flag.is_(True)).order_by(HADevice.area_name, HADevice.name)))
    assigned = ha._assigned(db)[role]
    return [
        HADeviceRead.model_validate(d).model_copy(update={"assigned_spot_ids": assigned.get(d.device_id, [])})
        for d in devices
    ]


@router.get("/issues", response_model=list[HAIssue], summary="Spots whose assigned HA device has gone or lost its label")
def list_issues(db: DB, _: CurrentUser) -> list[dict]:
    return ha.list_issues(db)
