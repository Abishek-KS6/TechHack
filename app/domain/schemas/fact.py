"""
BrandShield AI - Pydantic v2 Domain Schemas for Substantiated Approved Facts.
"""

from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class ApprovedFactBase(BaseModel):
    fact_statement: str = Field(..., min_length=5)
    original_source_url: str = Field(..., min_length=10)
    evidence_excerpt: str = Field(..., min_length=10)
    verification_date: datetime
    expiry_date: datetime


class ApprovedFactCreate(ApprovedFactBase):
    workspace_id: uuid.UUID
    brand_profile_id: Optional[uuid.UUID] = None
    responsible_owner_id: uuid.UUID
    embedding: list[float] = Field(..., min_length=1536, max_length=1536)


class ApprovedFactUpdate(BaseModel):
    fact_statement: Optional[str] = Field(default=None, min_length=5)
    original_source_url: Optional[str] = Field(default=None, min_length=10)
    evidence_excerpt: Optional[str] = Field(default=None, min_length=10)
    verification_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    responsible_owner_id: Optional[uuid.UUID] = None
    embedding: Optional[list[float]] = Field(default=None, min_length=1536, max_length=1536)
    is_active: Optional[bool] = None


class ApprovedFactRead(ApprovedFactBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    brand_profile_id: Optional[uuid.UUID] = None
    responsible_owner_id: uuid.UUID
    last_updated_date: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FactTemporalQuery(BaseModel):
    workspace_id: uuid.UUID
    as_of: datetime = Field(default_factory=datetime.utcnow)
    include_stale: bool = False
