from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, ResponseModel, Timestamps


class UserRead(Timestamps):
    id: int
    username: str
    display_name: str | None
    is_admin: bool
    is_active: bool


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$")
    display_name: str | None = None
    password: str = Field(min_length=8)
    is_admin: bool = False


class UserUpdate(BaseModel):
    display_name: str | None = None
    password: str | None = Field(default=None, min_length=8)
    is_admin: bool | None = None
    is_active: bool | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class SetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$")
    display_name: str | None = None
    password: str = Field(min_length=8)


class AuthStatus(ResponseModel):
    setup_required: bool
    user: UserRead | None
    ingress: bool = False


class ApiTokenRead(ORMModel):
    id: int
    name: str
    prefix: str
    user_id: int
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class ApiTokenCreated(ApiTokenRead):
    token: str = Field(description="The full token. Shown only once.")
