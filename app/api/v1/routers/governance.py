"""
BrandShield AI - Enterprise Governance & Audit Verification Router.
Provides cryptographic verification of the SHA-256 Merkle-style audit chain,
single-pass multi-dimensional governance reporting (GROUP BY CUBE / CTEs),
evidence traceability grounding audits, and automated labelled test set benchmarks.
"""

from typing import Annotated, Any, Optional
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import RequireRole
from app.domain.enums import UserRole
from app.domain.schemas.audit import AuditChainVerificationResult
from app.domain.schemas.governance import (
    EvaluationBenchmarkResponse,
    GovernanceReportResponse,
    TraceabilityMetricsResponse,
)
from app.infrastructure.db.models import User
from app.infrastructure.db.session import get_async_session
from app.services.audit_service import AuditService
from app.services.governance.evaluator import GovernanceEvaluator
from app.services.governance.reporting_service import GovernanceReportService
from app.services.governance.retention_reaper import RetentionReaperService
from app.services.governance.traceability_service import TraceabilityAuditService

router = APIRouter()

AuthorizedAdmin = Annotated[User, Depends(RequireRole(UserRole.ADMINISTRATOR))]
AuthorizedAuditor = Annotated[User, Depends(RequireRole(UserRole.REVIEWER, UserRole.ADMINISTRATOR))]


@router.post(
    "/audit-verify",
    response_model=AuditChainVerificationResult,
    summary="Verify Cryptographic Audit Ledger Integrity",
)
@router.get(
    "/audit-verify",
    response_model=AuditChainVerificationResult,
    summary="Verify Cryptographic Audit Ledger Integrity",
)
async def verify_audit_chain_integrity(
    admin: AuthorizedAdmin,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AuditChainVerificationResult:
    """
    Mathematically verifies the integrity of the entire append-only SHA-256 audit chain.
    Traverses every block sequentially, validating cryptographic linkages (previous_hash)
    and content hashes (current_hash) to prove zero database tampering.
    """
    return await AuditService.verify_chain_integrity(
        session=session,
        workspace_id=admin.workspace_id,
    )


@router.get(
    "/reports",
    response_model=GovernanceReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Governance Compliance Metrics & Severity CUBE Report",
)
async def get_governance_report(
    auditor: AuthorizedAuditor,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    brand_profile_id: Optional[uuid.UUID] = Query(None, description="Optional brand profile filter"),
) -> GovernanceReportResponse:
    """
    Executes single-pass PostgreSQL aggregations (GROUP BY CUBE / CTEs) so reported
    issue-category counts (TONE, TERMINOLOGY, MESSAGING, STALE_FACT, UNSUPPORTED_CLAIM, ACCESSIBILITY)
    and severity distributions mathematically match underlying findings records with 100% precision.
    """
    return await GovernanceReportService.generate_report(
        session=session,
        workspace_id=auditor.workspace_id,
        brand_profile_id=brand_profile_id,
    )


@router.get(
    "/traceability-metrics",
    response_model=TraceabilityMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Evidence Traceability & Evidence-Linked Grounding Audit",
)
async def get_traceability_metrics(
    auditor: AuthorizedAuditor,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    brand_profile_id: Optional[uuid.UUID] = Query(None, description="Optional brand profile filter"),
) -> TraceabilityMetricsResponse:
    """
    Computes the exact percentage of findings that possess a valid, non-null supporting
    linked_guideline_id or linked_fact_id reference, proving zero ungrounded violation claims.
    """
    return await TraceabilityAuditService.compute_metrics(
        session=session,
        workspace_id=auditor.workspace_id,
        brand_profile_id=brand_profile_id,
    )


@router.post(
    "/evaluate-testset",
    response_model=EvaluationBenchmarkResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Automated Labelled Test Set Benchmark Evaluation",
)
async def evaluate_labelled_testset(
    auditor: AuthorizedAuditor,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    brand_profile_id: Optional[uuid.UUID] = Query(None, description="Optional brand profile to benchmark"),
) -> EvaluationBenchmarkResponse:
    """
    Executes the analysis pipeline against a built-in labelled evaluation dataset
    containing 15 realistic corporate content samples with known ground-truth violations
    (outdated statistics, unapproved superlatives, off-brand tone, terminology conflicts,
    and clean baseline passages).
    Computes True Positives, False Positives, False Negatives, Precision, Recall, F1 Score, and P95 latency.
    """
    return await GovernanceEvaluator.run_benchmark(
        session=session,
        workspace_id=auditor.workspace_id,
        brand_profile_id=brand_profile_id,
    )


@router.post(
    "/enforce-retention",
    status_code=status.HTTP_200_OK,
    summary="Execute Limited-Retention TTL Policy Reaper",
)
async def enforce_data_retention(
    auditor: AuthorizedAuditor,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    retention_days: Optional[int] = Query(None, description="Override TTL retention window in days"),
    dry_run: bool = Query(False, description="Simulate purge without mutating records"),
) -> dict[str, Any]:
    """
    Limited-Retention TTL Reaper:
    Scans for submissions older than brand retention policy (e.g. 30 days).
    Cryptographically shreds raw text while preserving finding counts and audit logs.
    Records RETENTION_POLICY_PURGED events in the cryptographic ledger.
    """
    result = await RetentionReaperService.enforce_retention(
        session=session,
        workspace_id=auditor.workspace_id,
        forced_retention_days=retention_days,
        dry_run=dry_run,
    )
    return result.to_dict()
