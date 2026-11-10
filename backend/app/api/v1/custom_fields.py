from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.auth.deps import DB, AdminUser, CurrentUser
from app.models import CustomFieldDefinition
from app.models.enums import CustomFieldEntity, CustomFieldType
from app.schemas.custom_field import CustomFieldCreate, CustomFieldRead, CustomFieldUpdate
from app.services.crud import apply_update, commit, get_or_404

router = APIRouter(prefix="/custom-fields", tags=["custom fields"])


def _check_options(type_: str, options: list[str] | None) -> None:
    if type_ == CustomFieldType.select and not options:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Select fields need at least one option")


@router.get("", response_model=list[CustomFieldRead])
def list_fields(db: DB, _: CurrentUser, entity: CustomFieldEntity | None = None) -> list[CustomFieldDefinition]:
    stmt = select(CustomFieldDefinition).order_by(
        CustomFieldDefinition.entity, CustomFieldDefinition.sort_order, CustomFieldDefinition.label
    )
    if entity:
        stmt = stmt.where(CustomFieldDefinition.entity == entity.value)
    return list(db.scalars(stmt))


@router.post("", response_model=CustomFieldRead, status_code=201)
def create_field(payload: CustomFieldCreate, db: DB, _: AdminUser) -> CustomFieldDefinition:
    _check_options(payload.type, payload.options)
    field = CustomFieldDefinition(**payload.model_dump(mode="json"))
    db.add(field)
    commit(db, f"A {payload.entity} field with key '{payload.key}' already exists")
    return field


@router.get("/{field_id}", response_model=CustomFieldRead)
def get_field(field_id: int, db: DB, _: CurrentUser) -> CustomFieldDefinition:
    return get_or_404(db, CustomFieldDefinition, field_id, "Custom field")


@router.patch("/{field_id}", response_model=CustomFieldRead)
def update_field(field_id: int, payload: CustomFieldUpdate, db: DB, _: AdminUser) -> CustomFieldDefinition:
    field = get_or_404(db, CustomFieldDefinition, field_id, "Custom field")
    apply_update(field, payload)
    _check_options(field.type, field.options)
    commit(db)
    return field


@router.delete(
    "/{field_id}", status_code=204, summary="Delete a field definition (existing values are kept but hidden)"
)
def delete_field(field_id: int, db: DB, _: AdminUser) -> None:
    db.delete(get_or_404(db, CustomFieldDefinition, field_id, "Custom field"))
    db.commit()
