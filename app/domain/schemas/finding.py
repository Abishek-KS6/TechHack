"""
BrandShield AI - Pydantic v2 Domain Schemas for Analysis Findings and Creator Actions.
"""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import CreatorAction, DetectorSource, FindingCategory, SeverityLevel, TriageStatus


class FindingBase(BaseModel):
    issue_category: FindingCategory
    severity: SeverityLevel
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    triage_status: TriageStatus
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., ge=0)
    explanation_reason: str = Field(..., min_length=5)
    suggested_correction: Optional[str] = None
    detector_source: DetectorSource
    is_automation_bias_audit: bool = False


class FindingCreate(FindingBase):
    revision_id: uuid.UUID
    linked_guideline_id: Optional[uuid.UUID] = None
    linked_fact_id: Optional[uuid.UUID] = None


class FindingUpdateAction(BaseModel):
    creator_action: CreatorAction
    creator_comment: Optional[str] = None


class FindingRead(FindingBase):
    id: uuid.UUID
    revision_id: uuid.UUID
    linked_guideline_id: Optional[uuid.UUID]
    linked_fact_id: Optional[uuid.UUID]
    creator_action: CreatorAction
    creator_comment: Optional[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
