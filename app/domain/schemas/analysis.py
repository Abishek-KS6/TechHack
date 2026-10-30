"""
BrandShield AI - Pydantic v2 Schemas for Intelligence Pipeline & Triage API.
"""

from datetime import datetime
from typing import Any, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import FindingCategory, SeverityLevel, TriageStatus
from app.domain.schemas.finding import FindingBase, FindingRead


class AnalysisPipelineRunRequest(BaseModel):
    """Payload to trigger the 4-stage intelligence pipeline on an immutable revision."""
    revision_id: uuid.UUID
    brand_profile_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional brand profile override (defaults to submission's profile)"
    )
    requested_provider: str = Field(
        default="Azure OpenAI",
        description="Requested LLM provider for tone evaluation (subject to privacy-gated boundary)"
    )
    audit_sample_rate: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional override for stochastic shadow audit sample rate"
    )


class AnalysisPipelineResultResponse(BaseModel):
    """Structured response detailing the findings and performance of the 4-stage intelligence pipeline."""
    revision_id: uuid.UUID
    submission_id: Optional[uuid.UUID] = None
    total_findings: int
    flagged_high_confidence: int
    routed_to_human_low_confidence: int
    stale_facts_to_reverify: int
    needs_verification_missing_evidence: int
    automation_bias_audits_injected: int
    processing_duration_ms: float
    findings: list[FindingRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AdHocAnalysisRequest(BaseModel):
    """Payload for real-time live-editor compliance analysis without requiring saved documents."""
    content_text: str = Field(..., min_length=1, description="Raw text or Markdown to analyze")
    brand_profile_id: uuid.UUID = Field(..., description="Target brand profile defining tone & rules")
    requested_provider: str = Field(default="Azure OpenAI", description="Requested LLM provider")


class AdHocFinding(BaseModel):
    """Lightweight finding structure for live editor feedback."""
    issue_category: FindingCategory
    severity: SeverityLevel
    confidence_score: float
    triage_status: TriageStatus
    start_offset: int
    end_offset: int
    explanation_reason: str
    suggested_correction: Optional[str] = None
    detector_source: str
    is_automation_bias_audit: bool = False
    linked_guideline_id: Optional[uuid.UUID] = None
    linked_fact_id: Optional[uuid.UUID] = None
    evidence_source: Optional[str] = None
    evidence_link: Optional[str] = None


class AdHocAnalysisResponse(BaseModel):
    """Real-time response for live editor feedback."""
    brand_profile_id: uuid.UUID
    total_findings: int
    processing_duration_ms: float
    findings: list[AdHocFinding] = Field(default_factory=list)


class AnalysisEngineStatusResponse(BaseModel):
    """Operational status and telemetry of the intelligence subsystem."""
    service: str = "BrandShield Intelligence Pipeline"
    stages: list[str] = [
        "Stage 1: Deterministic Rule Engine (Aho-Corasick & AST)",
        "Stage 2: Temporal Fact & Hybrid RAG Retrieval Engine",
        "Stage 3: Privacy-Gated Boundary & Circuit-Breaker LLM Router",
        "Stage 4: Confidence Triage & Automation-Bias Safeguard",
    ]
    circuit_breaker_state: str
    circuit_breaker_available: bool
    fallback_cache_size: int
    supported_providers: list[str] = [
        "Azure OpenAI (Zero-Data-Retention)",
        "Anthropic (Commercial VPC)",
        "AWS Bedrock",
    ]
