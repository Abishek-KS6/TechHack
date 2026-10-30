"""
BrandShield AI - Enterprise Governance Reporting, Traceability & Benchmark Schemas.
Pydantic v2 domain contracts for compliance intelligence reports, traceability audits,
and evaluation test set benchmarks.
"""

from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class CategorySeverityCount(BaseModel):
    """Multi-dimensional aggregation cell from PostgreSQL GROUP BY CUBE(issue_category, severity)."""
    issue_category: Optional[str] = Field(None, description="Compliance category or None for subtotal")
    severity: Optional[str] = Field(None, description="Severity tier or None for subtotal")
    count: int = Field(..., ge=0, description="Exact finding count matching this dimensional slice")


class RechartsCategoryBar(BaseModel):
    """Pre-formatted row for Recharts <BarChart> displaying recurring issue categories."""
    category: str = Field(..., description="Finding category identifier")
    name: str = Field(..., description="Human-readable category label")
    count: int = Field(..., ge=0, description="Total occurrences")
    CRITICAL: int = Field(default=0, ge=0, description="Critical findings count")
    HIGH: int = Field(default=0, ge=0, description="High severity count")
    MEDIUM: int = Field(default=0, ge=0, description="Medium severity count")
    LOW: int = Field(default=0, ge=0, description="Low severity count")


class RechartsReviewTrendLine(BaseModel):
    """Pre-formatted time-series row for Recharts <LineChart> review trends."""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    approved: int = Field(default=0, ge=0, description="Approved sign-offs count")
    changes_requested: int = Field(default=0, ge=0, description="Changes requested count")
    total_reviews: int = Field(default=0, ge=0, description="Total review actions count")


class RechartsTriagePie(BaseModel):
    """Pre-formatted slice for Recharts <PieChart> displaying confidence triage distribution."""
    name: str = Field(..., description="Bucket or status label")
    value: int = Field(..., ge=0, description="Finding count in this bucket")
    fill: str = Field(..., description="Hex color code for slice fill")
    key: Optional[str] = Field(None, description="Machine-readable tier key")
    percentage: float = Field(default=0.0, ge=0.0, le=100.0, description="Percentage of total findings")


class GovernanceReportResponse(BaseModel):
    """
    Comprehensive enterprise governance compliance report.
    Guarantees 100% mathematical consistency with underlying findings via single-pass CUBE/CTE aggregations.
    Includes pre-formatted datasets ready for React Recharts components.
    """
    workspace_id: uuid.UUID
    brand_profile_id: Optional[uuid.UUID] = None
    total_findings: int = Field(..., ge=0, description="Total findings across evaluated scope")
    category_counts: dict[str, int] = Field(default_factory=dict, description="Counts by FindingCategory")
    severity_counts: dict[str, int] = Field(default_factory=dict, description="Counts by SeverityLevel")
    triage_status_counts: dict[str, int] = Field(default_factory=dict, description="Counts by TriageStatus")
    detector_source_counts: dict[str, int] = Field(default_factory=dict, description="Counts by DetectorSource")
    creator_action_counts: dict[str, int] = Field(default_factory=dict, description="Counts by CreatorAction")
    category_severity_cube: list[CategorySeverityCount] = Field(
        default_factory=list, description="Dimensional breakdown from GROUP BY CUBE"
    )
    recharts_category_bar: list[RechartsCategoryBar] = Field(
        default_factory=list, description="Recharts <BarChart> dataset for recurring issue categories"
    )
    recharts_review_trends_line: list[RechartsReviewTrendLine] = Field(
        default_factory=list, description="Recharts <LineChart> dataset for review decisions over time"
    )
    recharts_triage_pie: list[RechartsTriagePie] = Field(
        default_factory=list, description="Recharts <PieChart> dataset for triage confidence buckets"
    )
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TraceabilityMetricsResponse(BaseModel):
    """
    Evidence-linked and evidence traceability compliance verification audit.
    Proves that every violation claim is grounded in a verified guideline or fact.
    """
    workspace_id: uuid.UUID
    brand_profile_id: Optional[uuid.UUID] = None
    total_findings: int = Field(..., ge=0, description="Total findings evaluated")
    grounded_findings_count: int = Field(..., ge=0, description="Findings with valid guideline or fact reference")
    ungrounded_findings_count: int = Field(..., ge=0, description="Findings lacking citation evidence")
    traceability_percentage: float = Field(..., ge=0.0, le=100.0, description="Exact grounding compliance percentage")
    guideline_linked_count: int = Field(..., ge=0, description="Findings linked to a brand guideline")
    fact_linked_count: int = Field(..., ge=0, description="Findings linked to an approved fact")
    both_linked_count: int = Field(..., ge=0, description="Findings linked to both guideline and fact")
    unsubstantiated_claims_count: int = Field(..., ge=0, description="Claims flagged specifically as ungrounded")
    is_zero_ungrounded_verified: bool = Field(..., description="True if 100% of findings possess valid evidence grounding")
    audit_timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationSampleResult(BaseModel):
    """Per-sample benchmark execution result against ground-truth corporate sample."""
    sample_id: str
    title: str
    text: str
    ground_truth_categories: list[str] = Field(default_factory=list)
    detected_categories: list[str] = Field(default_factory=list)
    detected_findings_count: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    latency_ms: float = 0.0
    status: str = Field(..., description="PERFECT_MATCH, PARTIAL_MATCH, or CLEAN_PASS")


class EvaluationBenchmarkResponse(BaseModel):
    """
    Complete evaluation dataset benchmark report.
    Contains overall Precision, Recall, F1 score, and latency percentiles across the 15 labelled corporate samples.
    """
    total_samples: int = Field(..., ge=1)
    true_positives: int = Field(..., ge=0)
    false_positives: int = Field(..., ge=0)
    false_negatives: int = Field(..., ge=0)
    precision: float = Field(..., ge=0.0, le=1.0)
    recall: float = Field(..., ge=0.0, le=1.0)
    f1_score: float = Field(..., ge=0.0, le=1.0)
    p95_latency_ms: float = Field(..., ge=0.0)
    avg_latency_ms: float = Field(..., ge=0.0)
    min_latency_ms: float = Field(..., ge=0.0)
    max_latency_ms: float = Field(..., ge=0.0)
    samples: list[EvaluationSampleResult] = Field(default_factory=list)
    evaluated_at: datetime

    model_config = ConfigDict(from_attributes=True)
