from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.auth.deps import DB, CurrentUser
from app.auth.security import generate_api_token
from app.db import utcnow
from app.models import ApiToken
from app.schemas.user import ApiTokenCreate, ApiTokenCreated, ApiTokenRead
from app.services.crud import get_or_404

router = APIRouter(prefix="/tokens", tags=["api tokens"])


@router.get("", response_model=list[ApiTokenRead], summary="List your API tokens (admins see all)")
def list_tokens(db: DB, user: CurrentUser) -> list[ApiToken]:
    stmt = select(ApiToken).order_by(ApiToken.created_at.desc())
    if not user.is_admin:
        stmt = stmt.where(ApiToken.user_id == user.id)
    return list(db.scalars(stmt))


@router.post("", response_model=ApiTokenCreated, status_code=201, summary="Create an API token for integrations")
def create_token(payload: ApiTokenCreate, db: DB, user: CurrentUser) -> ApiTokenCreated:
    token, prefix, token_hash = generate_api_token()
    api_token = ApiToken(user_id=user.id, name=payload.name, prefix=prefix, token_hash=token_hash)
    db.add(api_token)
    db.commit()
    return ApiTokenCreated.model_validate({**ApiTokenRead.model_validate(api_token).model_dump(), "token": token})


@router.delete("/{token_id}", status_code=204, summary="Revoke an API token")
def revoke_token(token_id: int, db: DB, user: CurrentUser) -> None:
    api_token = get_or_404(db, ApiToken, token_id, "API token")
    if api_token.user_id != user.id and not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your token")
    if api_token.revoked_at is None:
        api_token.revoked_at = utcnow()
        db.commit()
