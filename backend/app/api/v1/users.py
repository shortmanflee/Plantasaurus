from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.auth.deps import DB, AdminUser, CurrentUser
from app.auth.security import hash_password
from app.models import User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.crud import commit, get_or_404

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(db: DB, _: CurrentUser) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.post("", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, db: DB, _: AdminUser) -> User:
    user = User(
        username=payload.username,
        display_name=payload.display_name or payload.username,
        password_hash=hash_password(payload.password),
        is_admin=payload.is_admin,
    )
    db.add(user)
    commit(db, f"Username '{payload.username}' is taken")
    return user


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: DB, _: CurrentUser) -> User:
    return get_or_404(db, User, user_id)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, db: DB, current: CurrentUser) -> User:
    user = get_or_404(db, User, user_id)
    is_self = user.id == current.id
    if not current.is_admin and not is_self:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit your own account")
    changes = payload.model_dump(exclude_unset=True)
    if not current.is_admin and ({"is_admin", "is_active"} & changes.keys()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can change roles or activation")
    if is_self and (changes.get("is_admin") is False or changes.get("is_active") is False):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "You cannot demote or disable yourself")
    if "password" in changes:
        if changes["password"]:
            user.password_hash = hash_password(changes.pop("password"))
        else:
            changes.pop("password")
    for key, value in changes.items():
        if value is not None:
            setattr(user, key, value)
    commit(db)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: DB, current: AdminUser) -> None:
    user = get_or_404(db, User, user_id)
    if user.id == current.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "You cannot delete yourself")
    db.delete(user)
    db.commit()
