"""
BrandShield AI - Pydantic v2 Domain Schemas for Submissions, Revisions, and Review Decisions.
"""

import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import CreatorAction, ReviewSignOff, WorkflowState


class DocumentRevisionBase(BaseModel):
    content_text: str = Field(..., min_length=1)
    ast_span_map: list[dict[str, Any]] = Field(default_factory=list)


class DocumentRevisionCreate(DocumentRevisionBase):
    parent_revision_id: Optional[uuid.UUID] = None


class DocumentRevisionRead(DocumentRevisionBase):
    id: uuid.UUID
    submission_id: uuid.UUID
    revision_number: int
    parent_revision_id: Optional[uuid.UUID]
    created_by_id: uuid.UUID
    sha256_content_hash: str
    diff_summary: Optional[dict[str, Any]]
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SubmissionBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    document_type: str = Field(..., min_length=2, max_length=32)
    brand_profile_id: uuid.UUID


class SubmissionCreate(SubmissionBase):
    workspace_id: uuid.UUID
    initial_content: str = Field(..., min_length=1)
    ast_span_map: list[dict[str, Any]] = Field(default_factory=list)


class TextSubmissionCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    brand_profile_id: uuid.UUID
    content: str = Field(..., min_length=1)
    document_type: str = Field(default="TEXT")


class SubmissionRead(SubmissionBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    creator_id: uuid.UUID
    assigned_reviewer_id: Optional[uuid.UUID]
    workflow_state: WorkflowState
    current_revision_id: Optional[uuid.UUID]
    version_number: Optional[int] = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("version_number", mode="before")
    @classmethod
    def default_version_number(cls, v: Any) -> int:
        return 1 if v is None else int(v)

    model_config = ConfigDict(from_attributes=True)


class ReviewDecisionCreate(BaseModel):
    decision: ReviewSignOff
    comments: str = Field(..., min_length=5)
    stipulations: Optional[dict[str, Any]] = None


class ReviewDecisionRead(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    revision_id: uuid.UUID
    reviewer_id: uuid.UUID
    decision: ReviewSignOff
    comments: str
    stipulations: Optional[dict[str, Any]]
    decided_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------------------
# Workflow & Revision Engine Schemas
# ------------------------------------------------------------------------------

class FindingResolutionRequest(BaseModel):
    """Payload submitted by creator to accept, reject, or edit a suggested finding correction."""
    action: CreatorAction = Field(..., description="Resolution action: ACCEPT, REJECT, or EDIT")
    edited_text: Optional[str] = Field(None, description="Custom replacement text if action is EDIT")
    comment: Optional[str] = Field(None, description="Optional rationale or justification from author")
    expected_version: Optional[int] = Field(None, description="Expected submission version_number for optimistic concurrency control")

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "custom_replacement" in data and not data.get("edited_text"):
                data["edited_text"] = data["custom_replacement"]
            if "rationale" in data and not data.get("comment"):
                data["comment"] = data["rationale"]
        return data

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, v: Any) -> Any:
        if isinstance(v, str):
            mapping = {
                "ACCEPT": CreatorAction.ACCEPTED,
                "ACCEPTED": CreatorAction.ACCEPTED,
                "ACCEPT_SUGGESTION": CreatorAction.ACCEPTED,
                "REJECT": CreatorAction.REJECTED,
                "REJECTED": CreatorAction.REJECTED,
                "REJECT_WITH_RATIONALE": CreatorAction.REJECTED,
                "EDIT": CreatorAction.EDITED,
                "EDITED": CreatorAction.EDITED,
                "CUSTOM_EDIT": CreatorAction.EDITED,
            }
            v_upper = v.upper()
            if v_upper in mapping:
                return mapping[v_upper]
        return v


class FindingResolutionResponse(BaseModel):
    """Result of resolving a finding, detailing action taken and new revision created if applicable."""
    finding_id: uuid.UUID
    action: CreatorAction
    applied_correction: Optional[str] = None
    new_revision_id: Optional[uuid.UUID] = None
    new_revision_number: Optional[int] = None
    submission_id: uuid.UUID
    workflow_state: WorkflowState
    comment: Optional[str] = None


class FindingVerificationInput(BaseModel):
    """Explicit reviewer confirmation for automation-bias audit findings."""
    finding_id: uuid.UUID
    verified: bool = True
    comment: Optional[str] = None


class InlineCommentInput(BaseModel):
    """Granular reviewer annotation on a specific span or finding."""
    finding_id: Optional[uuid.UUID] = None
    span_id: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    comment: str = Field(..., min_length=1)


class ReviewSubmissionRequest(BaseModel):
    """Comprehensive human reviewer determination payload."""
    decision: ReviewSignOff = Field(..., description="APPROVED or CHANGES_REQUESTED")
    comments: str = Field(..., min_length=5, description="Official reviewer notes and governance feedback")
    stipulations: Optional[dict[str, Any]] = Field(None, description="Conditional stipulations or regulatory disclosures")
    finding_verifications: Optional[list[FindingVerificationInput]] = Field(
        default=None,
        description="Explicit human verifications for findings flagged by the automation-bias safeguard",
    )
    inline_comments: Optional[list[InlineCommentInput]] = Field(
        default=None,
        description="Granular inline annotations attached to findings or character offsets",
    )


class TokenDiffChunk(BaseModel):
    """Side-by-side token-level difference chunk for rich UI rendering."""
    op: str = Field(..., description="Diff operation: equal, insert, delete, replace")
    old_text: str = Field(default="", description="Token text from base revision")
    new_text: str = Field(default="", description="Token text from compared revision")
    old_start: int = Field(..., description="Start character offset in base text")
    old_end: int = Field(..., description="End character offset in base text")
    new_start: int = Field(..., description="Start character offset in compared text")
    new_end: int = Field(..., description="End character offset in compared text")


class RevisionDiffResponse(BaseModel):
    """Complete revision lineage and exact side-by-side token and unified diffs."""
    submission_id: uuid.UUID
    from_revision: int
    to_revision: int
    from_revision_id: uuid.UUID
    to_revision_id: uuid.UUID
    lineage: list[DocumentRevisionRead]
    unified_diff: list[str]
    token_diff: list[TokenDiffChunk]
    lines_added: int
    lines_removed: int

