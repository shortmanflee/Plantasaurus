from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import SESSION_COOKIE, hash_token, session_matches
from app.config import get_settings
from app.db import get_db, utcnow
from app.models import ApiToken, User

DB = Annotated[Session, Depends(get_db)]


def _user_from_ingress(request: Request, db: Session) -> User | None:
    settings = get_settings()
    if not settings.ingress_mode:
        return None
    client = request.client.host if request.client else None
    if client not in settings.ingress_trusted_ips:
        return None
    ha_id = request.headers.get("X-Remote-User-Id")
    if not ha_id:
        return None
    user = db.scalar(select(User).where(User.ha_user_id == ha_id))
    if user is None:
        username = request.headers.get("X-Remote-User-Name") or f"ha_{ha_id[:8]}"
        if db.scalar(select(User).where(User.username == username)):
            username = f"{username}_{ha_id[:6]}"
        is_first = db.scalar(select(User.id).limit(1)) is None
        user = User(
            username=username,
            display_name=request.headers.get("X-Remote-User-Display-Name") or username,
            ha_user_id=ha_id,
            is_admin=is_first,
        )
        db.add(user)
        db.commit()
    return user


def _user_from_token(request: Request, db: Session) -> User | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    api_token = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(token.strip())))
    if api_token is None or api_token.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked API token")
    api_token.last_used_at = utcnow()
    db.commit()
    return api_token.user


def _user_from_session(request: Request, db: Session) -> User | None:
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    parsed = request.app.state.session_signer.loads(cookie)
    if parsed is None:
        return None
    uid, fingerprint = parsed
    user = db.get(User, uid)
    if user is None or not session_matches(user.password_hash, fingerprint):
        return None
    return user


def get_optional_user(request: Request, db: DB) -> User | None:
    user = _user_from_token(request, db) or _user_from_ingress(request, db) or _user_from_session(request, db)
    if user is not None and not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is disabled")
    return user


def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_admin_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin privileges required")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(get_admin_user)]
