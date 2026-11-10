from datetime import date
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CustomFieldDefinition
from app.models.enums import CustomFieldType


def validate_attributes(
    db: Session, entity: str, attrs: dict[str, Any] | None, existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Validate an `attributes` dict against the custom field definitions for an entity.

    Values are merged into `existing` (PATCH semantics); a null/empty value removes a key.
    Keys whose definition was deleted are preserved untouched.
    """
    merged = dict(existing or {})
    if not attrs:
        return merged
    defs = {d.key: d for d in db.scalars(select(CustomFieldDefinition).where(CustomFieldDefinition.entity == entity))}
    errors: list[str] = []
    cleaned: dict[str, Any] = {}
    for key, value in attrs.items():
        if value is None or value == "":
            merged.pop(key, None)
            continue
        d = defs.get(key)
        if d is None:
            if existing and existing.get(key) == value:
                continue
            errors.append(f"Unknown {entity} field '{key}'")
            continue
        try:
            cleaned[key] = _coerce(d, value)
        except ValueError as exc:
            errors.append(f"{d.label}: {exc}")
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(errors))
    merged.update(cleaned)
    return merged


def _coerce(d: CustomFieldDefinition, value: Any) -> Any:
    match CustomFieldType(d.type):
        case CustomFieldType.text:
            return str(value)
        case CustomFieldType.number:
            if isinstance(value, bool):
                raise ValueError("expected a number")
            return float(value)
        case CustomFieldType.bool:
            if not isinstance(value, bool):
                raise ValueError("expected true/false")
            return value
        case CustomFieldType.date:
            return date.fromisoformat(str(value)).isoformat()
        case CustomFieldType.select:
            if d.options and value not in d.options:
                raise ValueError(f"must be one of {', '.join(d.options)}")
            return value
