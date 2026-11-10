from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.auth.deps import DB, CurrentUser, get_optional_user
from app.auth.security import SESSION_COOKIE, hash_password, verify_password
from app.config import get_settings
from app.models import User
from app.schemas.user import AuthStatus, LoginRequest, SetupRequest, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session(request: Request, response: Response, user: User) -> None:
    signer = request.app.state.session_signer
    response.set_cookie(
        SESSION_COOKIE,
        signer.dumps(user.id, user.password_hash),
        max_age=signer.max_age,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
        path="/",
    )


@router.get("/status", response_model=AuthStatus, summary="Whether first-run setup is needed, and who is logged in")
def auth_status(request: Request, db: DB) -> AuthStatus:
    setup_required = db.scalar(select(User.id).limit(1)) is None
    user = None
    if not setup_required:
        try:
            user = get_optional_user(request, db)
        except HTTPException:
            user = None
    return AuthStatus(
        setup_required=setup_required,
        user=UserRead.model_validate(user) if user else None,
        ingress=get_settings().ingress_mode,
    )


@router.post("/setup", response_model=UserRead, status_code=201, summary="Create the first admin user")
def setup(payload: SetupRequest, request: Request, response: Response, db: DB) -> User:
    if db.scalar(select(User.id).limit(1)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Setup has already been completed")
    user = User(
        username=payload.username,
        display_name=payload.display_name or payload.username,
        password_hash=hash_password(payload.password),
        is_admin=True,
    )
    db.add(user)
    db.commit()
    _set_session(request, response, user)
    return user


@router.post("/login", response_model=UserRead)
def login(payload: LoginRequest, request: Request, response: Response, db: DB) -> User:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    _set_session(request, response, user)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user
