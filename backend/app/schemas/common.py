from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ResponseModel(BaseModel):
    """Fields with defaults are always present in responses, so mark them required in the schema."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class ORMModel(ResponseModel):
    model_config = ConfigDict(from_attributes=True, json_schema_serialization_defaults_required=True)


class Timestamps(ORMModel):
    created_at: datetime
    updated_at: datetime


class Page(ResponseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class Message(BaseModel):
    detail: str
