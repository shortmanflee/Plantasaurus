from fastapi import APIRouter

from app.api.v1 import (
    assessments,
    auth,
    custom_fields,
    events,
    homeassistant,
    insights,
    instances,
    locations,
    mcp,
    media,
    plants,
    tokens,
    users,
)

api_router = APIRouter(prefix="/api/v1")
for module in (auth, users, tokens, plants, locations, instances, events, assessments, media, custom_fields, insights, homeassistant, mcp):
    api_router.include_router(module.router)


@api_router.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
