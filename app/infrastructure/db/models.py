"""
BrandShield AI - Enterprise Database Domain Models
Production-Grade Asynchronous PostgreSQL Schema with pgvector and strict constraints.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from app.infrastructure.db.custom_types import PortableVector, PortableSearchVector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    AuditAction,
    CreatorAction,
    DetectorSource,
    FindingCategory,
    GuidelineCategory,
    ReviewSignOff,
    SeverityLevel,
    TriageStatus,
    UserRole,
    WorkflowState,
)
from app.infrastructure.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# ==============================================================================
# Custom PostgreSQL Native Enum Types
# ==============================================================================

user_role_enum = ENUM(
    UserRole,
    name="user_role_enum",
    create_type=False,
    metadata=Base.metadata,
)
workflow_state_enum = ENUM(
    WorkflowState,
    name="workflow_state_enum",
    create_type=False,
    metadata=Base.metadata,
)
guideline_category_enum = ENUM(
    GuidelineCategory,
    name="guideline_category_enum",
    create_type=False,
    metadata=Base.metadata,
)
finding_category_enum = ENUM(
    FindingCategory,
    name="finding_category_enum",
    create_type=False,
    metadata=Base.metadata,
)
severity_level_enum = ENUM(
    SeverityLevel,
    name="severity_level_enum",
    create_type=False,
    metadata=Base.metadata,
)
triage_status_enum = ENUM(
    TriageStatus,
    name="triage_status_enum",
    create_type=False,
    metadata=Base.metadata,
)
detector_source_enum = ENUM(
    DetectorSource,
    name="detector_source_enum",
    create_type=False,
    metadata=Base.metadata,
)
creator_action_enum = ENUM(
    CreatorAction,
    name="creator_action_enum",
    create_type=False,
    metadata=Base.metadata,
)
review_signoff_enum = ENUM(
    ReviewSignOff,
    name="review_signoff_enum",
    create_type=False,
    metadata=Base.metadata,
)


# ==============================================================================
# 1. Multi-Tenant Workspaces & RBAC Users
# ==============================================================================

class Workspace(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Multi-tenant isolation boundary for enterprise brand assets and policies.
    """
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Human-readable enterprise client organization name."
    )
    slug: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        doc="URL-safe unique identifier for tenant routing."
    )
    api_key_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        doc="SHA-256 hash of provisioned programmatic API key."
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default=text("true"),
        doc="Soft-disable flag for suspended enterprise tenants."
    )
    review_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "confidence_threshold": 0.85,
            "random_double_check_percentage": 15.0,
            "fact_review_period_days": 90,
            "require_evidence_before_approval": True,
        },
        server_default=text(
            '\'{"confidence_threshold": 0.85, "random_double_check_percentage": 15.0, "fact_review_period_days": 90, "require_evidence_before_approval": true}\'::jsonb'
        ),
        doc="Configurable review rules: confidence_threshold, random_double_check_percentage, fact_review_period_days, require_evidence_before_approval."
    )

    # Relationships
    users: Mapped[list[User]] = relationship(
        "User",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    brand_profiles: Mapped[list[BrandProfile]] = relationship(
        "BrandProfile",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    approved_facts: Mapped[list[ApprovedFact]] = relationship(
        "ApprovedFact",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    submissions: Mapped[list[Submission]] = relationship(
        "Submission",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_logs: Mapped[list[AuditLedger]] = relationship(
        "AuditLedger",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Enterprise actor supporting strict RBAC: CREATOR, REVIEWER, ADMINISTRATOR.
    """
    __tablename__ = "users"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent tenant identifier."
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="Primary login identity."
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Bcrypt/Argon2 password hash."
    )
    full_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Legal actor display name."
    )
    role: Mapped[UserRole] = mapped_column(
        user_role_enum,
        nullable=False,
        index=True,
        doc="RBAC role governing platform authorization."
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default=text("true"),
        doc="Account active status flag."
    )

    # Constraints & Indexes
    __table_args__ = (
        UniqueConstraint("workspace_id", "email", name="uq_users_workspace_email"),
        Index("ix_users_workspace_role", "workspace_id", "role"),
    )

    # Relationships
    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="users")
    created_submissions: Mapped[list[Submission]] = relationship(
        "Submission",
        back_populates="creator",
        foreign_keys="Submission.creator_id",
    )
    assigned_submissions: Mapped[list[Submission]] = relationship(
        "Submission",
        back_populates="assigned_reviewer",
        foreign_keys="Submission.assigned_reviewer_id",
    )
    created_revisions: Mapped[list[DocumentRevision]] = relationship(
        "DocumentRevision",
        back_populates="created_by",
    )
    owned_facts: Mapped[list[ApprovedFact]] = relationship(
        "ApprovedFact",
        back_populates="responsible_owner",
    )
    review_decisions: Mapped[list[ReviewDecision]] = relationship(
        "ReviewDecision",
        back_populates="reviewer",
    )


# ==============================================================================
# 2. Brand Profiles & Privacy Gate Configuration
# ==============================================================================

class BrandProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Configurable brand guidelines container, terminology matrices, and zero-trust privacy gate.
    """
    __tablename__ = "brand_profiles"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent tenant identifier."
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Brand profile identity (e.g., 'North America Enterprise B2B')."
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Contextual briefing and organizational scope."
    )
    tone_parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        doc="Target formality (1-10), enthusiasm, reading grade level, and forbidden sentiments."
    )
    banned_terminology_map: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        doc="Map of strictly prohibited terms -> {reason, violation_severity, suggested_replacements}."
    )
    preferred_terminology_map: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        doc="Map of deprecated or discouraged phrases -> approved corporate vocabulary."
    )
    messaging_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        doc="Mandatory legal disclaimers, required footnotes, and positioning directives."
    )
    privacy_gate_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "allow_external_llm": False,
            "approved_providers": [],
            "contract_verified_at": None,
            "retention_days": 30,
        },
        server_default=text(
            '\'{"allow_external_llm": false, "approved_providers": [], "contract_verified_at": null, "retention_days": 30}\'::jsonb'
        ),
        doc="Zero-trust privacy gate policy: external LLM egress clearance and data retention bounds."
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default=text("true"),
        doc="Active status flag."
    )

    # Constraints & Indexes
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_brand_profile_workspace_name"),
    )

    # Relationships
    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="brand_profiles")
    guidelines: Mapped[list[BrandGuideline]] = relationship(
        "BrandGuideline",
        back_populates="brand_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    submissions: Mapped[list[Submission]] = relationship(
        "Submission",
        back_populates="brand_profile",
    )


# ==============================================================================
# 3. Brand Guidelines (Hybrid RAG: Vector + Full-Text Search)
# ==============================================================================

class BrandGuideline(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Granular regulatory and brand directive clauses indexed with HNSW and GIN search vectors.
    """
    __tablename__ = "brand_guidelines"

    brand_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent brand profile."
    )
    clause_identifier: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Enterprise citation clause ID (e.g. 'SEC-TONE-01', 'LEGAL-DISCLAIMER-04')."
    )
    clause_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Normative compliance requirement and policy wording."
    )
    category: Mapped[GuidelineCategory] = mapped_column(
        guideline_category_enum,
        nullable=False,
        index=True,
        doc="Directive classification (TONE, TERMINOLOGY, MESSAGING, ACCESSIBILITY)."
    )
    severity: Mapped[SeverityLevel] = mapped_column(
        severity_level_enum,
        nullable=False,
        index=True,
        doc="Default enforcement severity if breached."
    )
    embedding: Mapped[list[float]] = mapped_column(
        PortableVector(1536),
        nullable=False,
        doc="1536-dimensional semantic dense vector representation."
    )
    search_vector: Mapped[str] = mapped_column(
        PortableSearchVector,
        Computed("to_tsvector('english', clause_text)", persisted=True),
        nullable=False,
        doc="Generated TSVECTOR index column for hybrid BM25 lexical retrieval."
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default=text("true"),
        doc="Active flag."
    )

    # Constraints & Indexes
    __table_args__ = (
        UniqueConstraint(
            "brand_profile_id", "clause_identifier", name="uq_guidelines_profile_clause"
        ),
        Index(
            "ix_brand_guidelines_profile_cat_sev",
            "brand_profile_id",
            "category",
            "severity",
        ),
        # HNSW Vector Index for dense cosine similarity (only if pgvector is enabled)
        *(
            [
                Index(
                    "ix_brand_guidelines_embedding_hnsw",
                    "embedding",
                    postgresql_using="hnsw",
                    postgresql_with={"m": 16, "ef_construction": 64},
                    postgresql_ops={"embedding": "vector_cosine_ops"},
                )
            ]
            if os.getenv("ENABLE_PGVECTOR", "false").lower() in ("true", "1", "yes")
            else []
        ),
        # GIN Full-Text Index for sparse keyword search
        Index(
            "ix_brand_guidelines_search_vector_gin",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    # Relationships
    brand_profile: Mapped[BrandProfile] = relationship(
        "BrandProfile", back_populates="guidelines"
    )
    findings: Mapped[list[Finding]] = relationship(
        "Finding", back_populates="linked_guideline"
    )


# ==============================================================================
# 4. Approved Facts & Temporal Staleness Engine
# ==============================================================================

class ApprovedFact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Substantiated ground-truth repository carrying strict verification windows.
    Evidence-linked safeguard rejects ungrounded or expired marketing statements.
    """
    __tablename__ = "approved_facts"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent tenant boundary."
    )
    brand_profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
        doc="Optional brand profile association boundary."
    )
    fact_statement: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Factual marketing or quantitative claim approved by legal/clinical reviewers."
    )
    original_source_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Canonical URI or repository path containing primary substantiation."
    )
    evidence_excerpt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Exact excerpted citation proving the factual validity of the claim."
    )
    verification_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Timestamp when the claim was certified by compliance counsel."
    )
    last_updated_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
        doc="Timestamp of most recent substantive review or metric re-evaluation."
    )
    expiry_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Strict temporal validity threshold; facts past this timestamp trigger staleness triage."
    )
    responsible_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Internal corporate owner responsible for fact recertification."
    )
    embedding: Mapped[list[float]] = mapped_column(
        PortableVector(1536),
        nullable=False,
        doc="1536-dimensional dense embedding of the fact statement."
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default=text("true"),
        doc="Active flag."
    )

    # Constraints & Indexes
    __table_args__ = (
        CheckConstraint("expiry_date > verification_date", name="chk_facts_valid_expiry_window"),
        # Index tailored for rapid temporal staleness queries and background re-verification sweeps
        Index(
            "ix_approved_facts_workspace_expiry",
            "workspace_id",
            "expiry_date",
            "is_active",
        ),
        # HNSW index for sub-10ms semantic fact lookup (only if pgvector is enabled)
        *(
            [
                Index(
                    "ix_approved_facts_embedding_hnsw",
                    "embedding",
                    postgresql_using="hnsw",
                    postgresql_with={"m": 16, "ef_construction": 64},
                    postgresql_ops={"embedding": "vector_cosine_ops"},
                )
            ]
            if os.getenv("ENABLE_PGVECTOR", "false").lower() in ("true", "1", "yes")
            else []
        ),
    )

    # Relationships
    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="approved_facts")
    responsible_owner: Mapped[User] = relationship("User", back_populates="owned_facts")
    findings: Mapped[list[Finding]] = relationship("Finding", back_populates="linked_fact")

    @property
    def source_url(self) -> str:
        return self.original_source_url

    @source_url.setter
    def source_url(self, val: str) -> None:
        self.original_source_url = val


# ==============================================================================
# 5. Submissions & Immutable Git-Like Revision DAG
# ==============================================================================

class Submission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Root document entity tracking governance workflow progression.
    """
    __tablename__ = "submissions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent tenant identifier."
    )
    brand_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Brand profile against which this document is governed."
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Authoring user who submitted the asset."
    )
    assigned_reviewer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Assigned human reviewer for ambiguous triage and final sign-off."
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Asset document title or campaign name."
    )
    document_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Input MIME classification (e.g. 'PDF', 'DOCX', 'MARKDOWN')."
    )
    workflow_state: Mapped[WorkflowState] = mapped_column(
        workflow_state_enum,
        nullable=False,
        default=WorkflowState.SUBMITTED,
        index=True,
        doc="Current state machine location."
    )
    current_revision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "document_revisions.id",
            use_alter=True,
            name="fk_submissions_current_revision_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        doc="Pointer to tip revision in the immutable DAG."
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
        doc="Optimistic concurrency control version counter."
    )

    # Indexes
    __table_args__ = (
        Index("ix_submissions_workspace_state", "workspace_id", "workflow_state"),
        Index("ix_submissions_reviewer_state", "assigned_reviewer_id", "workflow_state"),
    )

    # Relationships
    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="submissions")
    brand_profile: Mapped[BrandProfile] = relationship("BrandProfile", back_populates="submissions")
    creator: Mapped[User] = relationship(
        "User", back_populates="created_submissions", foreign_keys=[creator_id]
    )
    assigned_reviewer: Mapped[Optional[User]] = relationship(
        "User", back_populates="assigned_submissions", foreign_keys=[assigned_reviewer_id]
    )
    revisions: Mapped[list[DocumentRevision]] = relationship(
        "DocumentRevision",
        back_populates="submission",
        foreign_keys="DocumentRevision.submission_id",
        order_by="DocumentRevision.revision_number",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    current_revision: Mapped[Optional[DocumentRevision]] = relationship(
        "DocumentRevision",
        foreign_keys=[current_revision_id],
        post_update=True,
    )
    review_decisions: Mapped[list[ReviewDecision]] = relationship(
        "ReviewDecision",
        back_populates="submission",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentRevision(Base, UUIDPrimaryKeyMixin):
    """
    Append-only revision node in the immutable document revision DAG.
    Original content is NEVER overwritten. Revisions form an explicit parent-child lineage.
    """
    __tablename__ = "document_revisions"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Root submission lineage."
    )
    revision_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Monotonically increasing ordinal revision number (1, 2, ...)."
    )
    parent_revision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_revisions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        doc="Pointer to parent revision node. Null only for initial genesis commit (v1)."
    )
    content_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Full immutable snapshot of parsed document text content."
    )
    ast_span_map: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        doc="Granular AST map linking sentence/clause spans to character offsets and visual coordinates."
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Actor committing this revision."
    )
    sha256_content_hash: Mapped[str] = mapped_column(
        CHAR(64),
        nullable=False,
        index=True,
        doc="SHA-256 cryptographic digest of content_text ensuring tamper detection."
    )
    diff_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        doc="Computed RFC 6902 JSON Patch or character-diff against parent revision."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        nullable=False,
        doc="Append-only revision creation timestamp."
    )

    # Constraints & Indexes
    __table_args__ = (
        CheckConstraint("revision_number >= 1", name="chk_revision_number_positive"),
        UniqueConstraint("submission_id", "revision_number", name="uq_submission_revision_number"),
        Index("ix_revisions_submission_created", "submission_id", "created_at"),
    )

    # Relationships
    submission: Mapped[Submission] = relationship(
        "Submission", back_populates="revisions", foreign_keys=[submission_id]
    )
    created_by: Mapped[User] = relationship("User", back_populates="created_revisions")
    parent_revision: Mapped[Optional[DocumentRevision]] = relationship(
        "DocumentRevision",
        remote_side="DocumentRevision.id",
        back_populates="child_revisions",
    )
    child_revisions: Mapped[list[DocumentRevision]] = relationship(
        "DocumentRevision",
        back_populates="parent_revision",
    )

    def get_decrypted_content(self) -> str:
        """Returns plaintext content, decrypting with envelope encryption if stored encrypted."""
        from app.core.crypto_storage import CryptoStorageEngine
        return CryptoStorageEngine.decrypt_content(self.content_text)

    findings: Mapped[list[Finding]] = relationship(
        "Finding",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    review_decisions: Mapped[list[ReviewDecision]] = relationship(
        "ReviewDecision",
        back_populates="revision",
    )


# ==============================================================================
# 6. Findings & Multi-Tier Confidence Triage Engine
# ==============================================================================

class Finding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Granular detection generated during document verification linked to an immutable revision.
    Enforces tri-state confidence triage and random anti-automation-bias audits.
    """
    __tablename__ = "findings"

    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent immutable revision snapshot."
    )
    issue_category: Mapped[FindingCategory] = mapped_column(
        finding_category_enum,
        nullable=False,
        index=True,
        doc="Category of detected compliance anomaly."
    )
    severity: Mapped[SeverityLevel] = mapped_column(
        severity_level_enum,
        nullable=False,
        index=True,
        doc="Finding severity level."
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Normalized algorithmic or model confidence score [0.0, 1.0]."
    )
    triage_status: Mapped[TriageStatus] = mapped_column(
        triage_status_enum,
        nullable=False,
        index=True,
        doc="Tri-state triage classification governing human vs. automated resolution."
    )
    start_offset: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Starting character offset in revision content_text."
    )
    end_offset: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Ending character offset in revision content_text."
    )
    explanation_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Actionable legal or policy justification for the finding."
    )
    suggested_correction: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Suggested replacement compliant with brand guidelines."
    )
    linked_guideline_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_guidelines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Direct pointer to breached guideline clause."
    )
    linked_fact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approved_facts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Direct pointer to substantiated fact or stale reference."
    )
    detector_source: Mapped[DetectorSource] = mapped_column(
        detector_source_enum,
        nullable=False,
        index=True,
        doc="Pipeline origin: DETERMINISTIC_RULE, TEMPORAL_FACT_MATCHER, or EXTERNAL_LLM."
    )
    is_automation_bias_audit: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default=text("false"),
        index=True,
        doc="Stochastic double-check safeguard injected to prevent reviewer rubber-stamping."
    )
    creator_action: Mapped[CreatorAction] = mapped_column(
        creator_action_enum,
        nullable=False,
        default=CreatorAction.PENDING,
        server_default=text("'PENDING'"),
        index=True,
        doc="Resolution action taken by author (PENDING, ACCEPTED, REJECTED, EDITED)."
    )
    creator_comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Optional rationale provided by author if rejecting or editing the finding."
    )

    # Constraints & Indexes
    __table_args__ = (
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="chk_findings_confidence_range",
        ),
        CheckConstraint(
            "end_offset >= start_offset",
            name="chk_findings_offset_bounds",
        ),
        CheckConstraint(
            "start_offset >= 0",
            name="chk_findings_start_offset_non_negative",
        ),
        Index("ix_findings_revision_triage", "revision_id", "triage_status"),
        Index("ix_findings_revision_severity", "revision_id", "severity"),
        Index("ix_findings_audit_safeguard", "detector_source", "is_automation_bias_audit"),
    )

    # Relationships
    revision: Mapped[DocumentRevision] = relationship("DocumentRevision", back_populates="findings")
    linked_guideline: Mapped[Optional[BrandGuideline]] = relationship(
        "BrandGuideline", back_populates="findings"
    )
    linked_fact: Mapped[Optional[ApprovedFact]] = relationship(
        "ApprovedFact", back_populates="findings"
    )


# ==============================================================================
# 7. Review Decisions & Cryptographically Hash-Chained Audit Ledger
# ==============================================================================

class ReviewDecision(Base, UUIDPrimaryKeyMixin):
    """
    Formal human sign-off record executed by an authorized compliance Reviewer.
    """
    __tablename__ = "review_decisions"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Governed submission identifier."
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Specific revision snapshot evaluated."
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Reviewer identity executing the verdict."
    )
    decision: Mapped[ReviewSignOff] = mapped_column(
        review_signoff_enum,
        nullable=False,
        doc="Final human disposition: APPROVED or CHANGES_REQUESTED."
    )
    comments: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Detailed reviewer guidance, legal stipulations, or approval rationale."
    )
    stipulations: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        doc="Structured conditions or mandatory disclosures attached to approval."
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        nullable=False,
        doc="Timestamp of human governance determination."
    )

    # Constraints & Indexes
    __table_args__ = (
        Index("ix_review_decisions_submission_decided", "submission_id", "decided_at"),
    )

    # Relationships
    submission: Mapped[Submission] = relationship("Submission", back_populates="review_decisions")
    revision: Mapped[DocumentRevision] = relationship("DocumentRevision", back_populates="review_decisions")
    reviewer: Mapped[User] = relationship("User", back_populates="review_decisions")


class AuditLedger(Base):
    """
    Append-only, cryptographically hash-chained tamper-evident audit ledger.
    Every row commits: current_hash = SHA-256(previous_hash || actor_id || action || payload || timestamp).
    Provides zero-repudiation regulatory guarantees for FTC, FDA, and SEC compliance.
    """
    __tablename__ = "audit_ledger"

    sequence_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        doc="Monotonically increasing sequence index providing strict deterministic ordering."
    )
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        doc="Tenant boundary for multi-tenant audit isolation."
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User initiating the action (null if automated system daemon)."
    )
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="Domain operation (e.g., 'DOCUMENT_SUBMITTED', 'EXTERNAL_LLM_DISCLOSED')."
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        doc="Comprehensive state snapshot or cryptographic diff of the operation."
    )
    previous_hash: Mapped[str] = mapped_column(
        CHAR(64),
        nullable=False,
        doc="SHA-256 digest of the immediate predecessor audit row."
    )
    current_hash: Mapped[str] = mapped_column(
        CHAR(64),
        nullable=False,
        unique=True,
        index=True,
        doc="Cryptographic digest sealing this audit entry into the hash chain."
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        nullable=False,
        index=True,
        doc="Microsecond-accurate monotonic clock timestamp."
    )

    # Constraints & Indexes
    __table_args__ = (
        Index("ix_audit_ledger_workspace_timestamp", "workspace_id", "timestamp"),
        Index("ix_audit_ledger_action_timestamp", "action", "timestamp"),
    )

    # Relationships
    workspace: Mapped[Optional[Workspace]] = relationship("Workspace", back_populates="audit_logs")
    actor: Mapped[Optional[User]] = relationship("User")
