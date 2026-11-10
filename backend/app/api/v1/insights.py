from fastapi import APIRouter

from app.auth.deps import DB, CurrentUser
from app.services.insights import Summary, summary

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/summary", response_model=Summary, summary="Dashboard summary")
def get_summary(db: DB, _: CurrentUser) -> Summary:
    return summary(db)
