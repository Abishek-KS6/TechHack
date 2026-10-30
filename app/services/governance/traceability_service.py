"""
BrandShield AI - Evidence Traceability & Evidence-Linked Audit Service.
Verifies that detected violations possess authoritative evidence grounding
(linked_guideline_id or linked_fact_id) to eliminate ungrounded or hallucinated compliance claims.
"""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.governance import TraceabilityMetricsResponse


class TraceabilityAuditService:
    """
    Evidence Traceability Audit Engine.
    Executes a single-pass aggregation confirming that all automated violation citations
    trace back to an approved guideline clause or certified ground-truth fact.
    """

    TRACEABILITY_QUERY = text("""
        WITH scoped_findings AS (
            SELECT 
                f.id,
                f.linked_guideline_id,
                f.linked_fact_id,
                f.issue_category::text AS issue_category
            FROM findings f
            JOIN document_revisions dr ON f.revision_id = dr.id
            JOIN submissions s ON dr.submission_id = s.id
            WHERE s.workspace_id = :workspace_id
              AND (CAST(:brand_profile_id AS UUID) IS NULL OR s.brand_profile_id = CAST(:brand_profile_id AS UUID))
        )
        SELECT 
            COUNT(*) AS total_findings,
            COUNT(CASE WHEN linked_guideline_id IS NOT NULL OR linked_fact_id IS NOT NULL THEN 1 END) AS grounded_findings_count,
            COUNT(CASE WHEN linked_guideline_id IS NULL AND linked_fact_id IS NULL THEN 1 END) AS ungrounded_findings_count,
            COUNT(CASE WHEN linked_guideline_id IS NOT NULL THEN 1 END) AS guideline_linked_count,
            COUNT(CASE WHEN linked_fact_id IS NOT NULL THEN 1 END) AS fact_linked_count,
            COUNT(CASE WHEN linked_guideline_id IS NOT NULL AND linked_fact_id IS NOT NULL THEN 1 END) AS both_linked_count,
            COUNT(CASE WHEN issue_category = 'UNSUBSTANTIATED_CLAIM' THEN 1 END) AS unsubstantiated_claims_count
        FROM scoped_findings
    """)

    TRACEABILITY_QUERY_SQLITE = text("""
        WITH scoped_findings AS (
            SELECT 
                f.id,
                f.linked_guideline_id,
                f.linked_fact_id,
                f.issue_category AS issue_category
            FROM findings f
            JOIN document_revisions dr ON f.revision_id = dr.id
            JOIN submissions s ON dr.submission_id = s.id
            WHERE s.workspace_id = :workspace_id
              AND (:brand_profile_id IS NULL OR s.brand_profile_id = :brand_profile_id)
        )
        SELECT 
            COUNT(*) AS total_findings,
            COUNT(CASE WHEN linked_guideline_id IS NOT NULL OR linked_fact_id IS NOT NULL THEN 1 END) AS grounded_findings_count,
            COUNT(CASE WHEN linked_guideline_id IS NULL AND linked_fact_id IS NULL THEN 1 END) AS ungrounded_findings_count,
            COUNT(CASE WHEN linked_guideline_id IS NOT NULL THEN 1 END) AS guideline_linked_count,
            COUNT(CASE WHEN linked_fact_id IS NOT NULL THEN 1 END) AS fact_linked_count,
            COUNT(CASE WHEN linked_guideline_id IS NOT NULL AND linked_fact_id IS NOT NULL THEN 1 END) AS both_linked_count,
            COUNT(CASE WHEN issue_category = 'UNSUBSTANTIATED_CLAIM' THEN 1 END) AS unsubstantiated_claims_count
        FROM scoped_findings
    """)

    @classmethod
    async def compute_metrics(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        brand_profile_id: Optional[uuid.UUID] = None,
    ) -> TraceabilityMetricsResponse:
        """
        Computes the evidence grounding percentage across all findings in the tenant scope.
        """
        now = datetime.now(timezone.utc)

        params: dict[str, Any] = {
            "workspace_id": str(workspace_id),
            "brand_profile_id": str(brand_profile_id) if brand_profile_id else None,
        }

        bind = session.get_bind()
        query = cls.TRACEABILITY_QUERY_SQLITE if bind and bind.dialect.name == "sqlite" else cls.TRACEABILITY_QUERY
        result = await session.execute(query, params)
        row = result.fetchone() if hasattr(result, "fetchone") else None

        if row is not None:
            mapping = row._mapping if hasattr(row, "_mapping") else dict(zip(
                [
                    "total_findings",
                    "grounded_findings_count",
                    "ungrounded_findings_count",
                    "guideline_linked_count",
                    "fact_linked_count",
                    "both_linked_count",
                    "unsubstantiated_claims_count",
                ],
                row
            ))
            total = int(mapping.get("total_findings", 0))
            grounded = int(mapping.get("grounded_findings_count", 0))
            ungrounded = int(mapping.get("ungrounded_findings_count", 0))
            guideline_linked = int(mapping.get("guideline_linked_count", 0))
            fact_linked = int(mapping.get("fact_linked_count", 0))
            both_linked = int(mapping.get("both_linked_count", 0))
            unsubstantiated = int(mapping.get("unsubstantiated_claims_count", 0))
        else:
            total = 0
            grounded = 0
            ungrounded = 0
            guideline_linked = 0
            fact_linked = 0
            both_linked = 0
            unsubstantiated = 0

        # Exact traceability percentage calculation (100% when zero findings exist)
        if total == 0:
            traceability_pct = 100.0
            is_zero_ungrounded = True
        else:
            traceability_pct = round((grounded / total) * 100.0, 2)
            is_zero_ungrounded = (ungrounded == 0)

        return TraceabilityMetricsResponse(
            workspace_id=workspace_id,
            brand_profile_id=brand_profile_id,
            total_findings=total,
            grounded_findings_count=grounded,
            ungrounded_findings_count=ungrounded,
            traceability_percentage=traceability_pct,
            guideline_linked_count=guideline_linked,
            fact_linked_count=fact_linked,
            both_linked_count=both_linked,
            unsubstantiated_claims_count=unsubstantiated,
            is_zero_ungrounded_verified=is_zero_ungrounded,
            audit_timestamp=now,
        )
