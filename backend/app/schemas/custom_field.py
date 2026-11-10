from pydantic import BaseModel, Field

from app.models.enums import CustomFieldEntity, CustomFieldType
from app.schemas.common import Timestamps


class CustomFieldBase(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    type: CustomFieldType
    options: list[str] | None = None
    help_text: str | None = None
    sort_order: int = 0


class CustomFieldCreate(CustomFieldBase):
    entity: CustomFieldEntity
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")


class CustomFieldUpdate(BaseModel):
    label: str | None = None
    options: list[str] | None = None
    help_text: str | None = None
    sort_order: int | None = None


class CustomFieldRead(CustomFieldBase, Timestamps):
    id: int
    entity: CustomFieldEntity
    key: str
