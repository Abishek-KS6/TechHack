"""
BrandShield AI - Pydantic v2 Domain Schemas for Brand Profiles, Guidelines, and Privacy Gate.
"""

from datetime import datetime
from typing import Any, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import GuidelineCategory, SeverityLevel


class PrivacyGateConfigSchema(BaseModel):
    allow_external_llm: bool = False
    approved_providers: list[str] = Field(default_factory=list)
    contract_verified_at: Optional[datetime] = None
    retention_days: int = Field(default=30, ge=1, le=3650)


class PrivacyGateConfigUpdate(BaseModel):
    allow_external_llm: Optional[bool] = None
    approved_providers: Optional[list[str]] = None
    contract_verified_at: Optional[datetime] = None
    retention_days: Optional[int] = Field(default=None, ge=1, le=3650)


class BrandProfileBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    description: Optional[str] = None
    tone_parameters: dict[str, Any] = Field(default_factory=dict)
    banned_terminology_map: dict[str, Any] = Field(default_factory=dict)
    preferred_terminology_map: dict[str, Any] = Field(default_factory=dict)
    messaging_rules: dict[str, Any] = Field(default_factory=dict)
    privacy_gate_config: PrivacyGateConfigSchema = Field(default_factory=PrivacyGateConfigSchema)


class BrandProfileCreate(BrandProfileBase):
    workspace_id: uuid.UUID


class BrandProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=128)
    description: Optional[str] = None
    tone_parameters: Optional[dict[str, Any]] = None
    banned_terminology_map: Optional[dict[str, Any]] = None
    preferred_terminology_map: Optional[dict[str, Any]] = None
    messaging_rules: Optional[dict[str, Any]] = None
    privacy_gate_config: Optional[PrivacyGateConfigSchema] = None
    is_active: Optional[bool] = None


class BrandProfileRead(BrandProfileBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BrandGuidelineBase(BaseModel):
    clause_identifier: str = Field(..., min_length=3, max_length=64)
    clause_text: str = Field(..., min_length=10)
    category: GuidelineCategory
    severity: SeverityLevel


class BrandGuidelineCreate(BrandGuidelineBase):
    brand_profile_id: uuid.UUID
    embedding: list[float] = Field(..., min_length=1536, max_length=1536)


class BrandGuidelineUpdate(BaseModel):
    clause_identifier: Optional[str] = Field(default=None, min_length=3, max_length=64)
    clause_text: Optional[str] = Field(default=None, min_length=10)
    category: Optional[GuidelineCategory] = None
    severity: Optional[SeverityLevel] = None
    embedding: Optional[list[float]] = Field(default=None, min_length=1536, max_length=1536)
    is_active: Optional[bool] = None


class BrandGuidelineRead(BrandGuidelineBase):
    id: uuid.UUID
    brand_profile_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
