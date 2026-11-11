from pydantic import BaseModel, Field

from app.schemas.common import ResponseModel


class MCPStatus(ResponseModel):
    available: bool = Field(description="False when PLANTASAURUS_MCP_ENABLED=false; the switch is then locked off")
    enabled: bool = Field(description="Whether /mcp currently accepts connections")
    path: str = Field(description="Endpoint path, relative to the app's base URL")


class MCPConfigUpdate(BaseModel):
    enabled: bool
