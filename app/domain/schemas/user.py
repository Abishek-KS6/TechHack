"""
BrandShield AI - Pydantic v2 Domain Schemas for Users, Workspaces, and Auth Tokens.
"""

from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import UserRole


class WorkspaceBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")


class WorkspaceCreate(WorkspaceBase):
    pass


class WorkspaceRead(WorkspaceBase):
    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=128)
    role: UserRole


class UserCreate(UserBase):
    workspace_id: uuid.UUID
    password: str = Field(..., min_length=8)


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2, max_length=128)
    role: UserRole = Field(default=UserRole.CREATOR)
    workspace_id: Optional[uuid.UUID] = None
    workspace_name: Optional[str] = None
    workspace_slug: Optional[str] = None


class UserRead(UserBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead
