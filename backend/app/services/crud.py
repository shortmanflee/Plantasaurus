from typing import Any, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

M = TypeVar("M")


def get_or_404(db: Session, model: type[M], obj_id: int, name: str | None = None) -> M:
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{name or model.__name__} {obj_id} not found")
    return obj


def apply_update(obj: Any, payload: BaseModel, exclude: set[str] | None = None) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True, exclude=exclude or set())
    for key, value in changes.items():
        setattr(obj, key, value)
    return changes


def paginate(db: Session, stmt: Select, limit: int, offset: int) -> tuple[list[Any], int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = list(db.scalars(stmt.limit(limit).offset(offset)).unique())
    return items, total


def commit(db: Session, conflict_detail: str = "Conflicts with an existing record") -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, conflict_detail) from exc


def ensure_exists(db: Session, model: type, obj_id: int | None, name: str) -> None:
    if obj_id is not None and db.get(model, obj_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{name} {obj_id} does not exist")
