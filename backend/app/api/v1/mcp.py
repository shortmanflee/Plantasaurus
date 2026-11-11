from fastapi import APIRouter, HTTPException, status

from app.auth.deps import DB, AdminUser, CurrentUser
from app.schemas.mcp import MCPConfigUpdate, MCPStatus
from app.services import mcp as svc

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _status(db) -> MCPStatus:
    return MCPStatus(available=svc.is_available(), enabled=svc.is_enabled(db), path="mcp")


@router.get("/status", response_model=MCPStatus, summary="Whether the MCP server is turned on")
def get_status(db: DB, _: CurrentUser) -> MCPStatus:
    return _status(db)


@router.put(
    "/config",
    response_model=MCPStatus,
    summary="Turn the MCP server on or off. Takes effect immediately, including for connected clients.",
)
def update_config(payload: MCPConfigUpdate, db: DB, _: AdminUser) -> MCPStatus:
    if not svc.is_available():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The MCP server is disabled by PLANTASAURUS_MCP_ENABLED=false"
        )
    svc.get_config(db).enabled = payload.enabled
    db.commit()
    return _status(db)
