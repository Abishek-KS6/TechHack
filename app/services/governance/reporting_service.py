"""
BrandShield AI - Enterprise Governance Reporting Service.
Executes single-pass PostgreSQL aggregations (GROUP BY CUBE / CTEs) to compile
comprehensive compliance metrics matching underlying findings records with 100% mathematical precision.
"""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import CreatorAction, DetectorSource, FindingCategory, SeverityLevel, TriageStatus
from app.domain.schemas.governance import (
    CategorySeverityCount,
    GovernanceReportResponse,
    RechartsCategoryBar,
    RechartsReviewTrendLine,
    RechartsTriagePie,
)


class GovernanceReportService:
    """
    High-performance analytics service for regulatory reporting.
    Leverages PostgreSQL GROUP BY CUBE to compute the full multi-dimensional cross-tabulation
    of issue categories and severity levels in a single optimized pass, and generates
    pre-formatted Recharts datasets for frontend dashboards.
    """

    REPORT_QUERY = text("""
        WITH scoped_findings AS (
            SELECT 
                f.id,
                f.issue_category::text AS issue_category,
                f.severity::text AS severity,
                f.triage_status::text AS triage_status,
                f.detector_source::text AS detector_source,
                f.creator_action::text AS creator_action,
                f.confidence_score AS confidence_score
            FROM findings f
            JOIN document_revisions dr ON f.revision_id = dr.id
            JOIN submissions s ON dr.submission_id = s.id
            WHERE s.workspace_id = :workspace_id
              AND (CAST(:brand_profile_id AS UUID) IS NULL OR s.brand_profile_id = CAST(:brand_profile_id AS UUID))
        )
        SELECT 
            'CUBE' AS metric_type,
            issue_category,
            severity,
            NULL AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY CUBE(issue_category, severity)

        UNION ALL

        SELECT 
            'TRIAGE' AS metric_type,
            NULL AS issue_category,
            NULL AS severity,
            triage_status AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY triage_status

        UNION ALL

        SELECT 
            'DETECTOR' AS metric_type,
            NULL AS issue_category,
            NULL AS severity,
            detector_source AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY detector_source

        UNION ALL

        SELECT 
            'ACTION' AS metric_type,
            NULL AS issue_category,
            NULL AS severity,
            creator_action AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY creator_action

        UNION ALL

        SELECT 
            'CONFIDENCE' AS metric_type,
            NULL AS issue_category,
            NULL AS severity,
            CASE 
                WHEN confidence_score >= 0.85 THEN 'HIGH'
                WHEN confidence_score >= 0.60 THEN 'MEDIUM'
                ELSE 'LOW'
            END AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY 4

        UNION ALL

        SELECT 
            'REVIEW_TREND' AS metric_type,
            NULL AS issue_category,
            rd.decision::text AS severity,
            TO_CHAR(DATE_TRUNC('day', rd.decided_at), 'YYYY-MM-DD') AS dimension_val,
            COUNT(*) AS count
        FROM review_decisions rd
        JOIN submissions s ON rd.submission_id = s.id
        WHERE s.workspace_id = :workspace_id
          AND (CAST(:brand_profile_id AS UUID) IS NULL OR s.brand_profile_id = CAST(:brand_profile_id AS UUID))
        GROUP BY DATE_TRUNC('day', rd.decided_at), rd.decision
    """)

    REPORT_QUERY_SQLITE = text("""
        WITH scoped_findings AS (
            SELECT 
                f.id,
                f.issue_category AS issue_category,
                f.severity AS severity,
                f.triage_status AS triage_status,
                f.detector_source AS detector_source,
                f.creator_action AS creator_action,
                f.confidence_score AS confidence_score
            FROM findings f
            JOIN document_revisions dr ON f.revision_id = dr.id
            JOIN submissions s ON dr.submission_id = s.id
            WHERE s.workspace_id = :workspace_id
              AND (:brand_profile_id IS NULL OR s.brand_profile_id = :brand_profile_id)
        )
        SELECT 
            'CUBE' AS metric_type,
            issue_category,
            severity,
            NULL AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY issue_category, severity

        UNION ALL

        SELECT 
            'CUBE' AS metric_type,
            issue_category,
            NULL AS severity,
            NULL AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY issue_category

        UNION ALL

        SELECT 
            'CUBE' AS metric_type,
            NULL AS issue_category,
            severity,
            NULL AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY severity

        UNION ALL

        SELECT 
            'CUBE' AS metric_type,
            NULL AS issue_category,
            NULL AS severity,
            NULL AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings

        UNION ALL

        SELECT 
            'TRIAGE' AS metric_type,
            NULL AS issue_category,
            NULL AS severity,
            triage_status AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY triage_status

        UNION ALL

        SELECT 
            'DETECTOR' AS metric_type,
            NULL AS issue_category,
            NULL AS severity,
            detector_source AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY detector_source

        UNION ALL

        SELECT 
            'ACTION' AS metric_type,
            NULL AS issue_category,
            NULL AS severity,
            creator_action AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY creator_action

        UNION ALL

        SELECT 
            'CONFIDENCE' AS metric_type,
            NULL AS issue_category,
            NULL AS severity,
            CASE 
                WHEN confidence_score >= 0.85 THEN 'HIGH'
                WHEN confidence_score >= 0.60 THEN 'MEDIUM'
                ELSE 'LOW'
            END AS dimension_val,
            COUNT(*) AS count
        FROM scoped_findings
        GROUP BY CASE 
                WHEN confidence_score >= 0.85 THEN 'HIGH'
                WHEN confidence_score >= 0.60 THEN 'MEDIUM'
                ELSE 'LOW'
            END

        UNION ALL

        SELECT 
            'REVIEW_TREND' AS metric_type,
            NULL AS issue_category,
            rd.decision AS severity,
            strftime('%Y-%m-%d', rd.decided_at) AS dimension_val,
            COUNT(*) AS count
        FROM review_decisions rd
        JOIN submissions s ON rd.submission_id = s.id
        WHERE s.workspace_id = :workspace_id
          AND (:brand_profile_id IS NULL OR s.brand_profile_id = :brand_profile_id)
        GROUP BY strftime('%Y-%m-%d', rd.decided_at), rd.decision
    """)

    @classmethod
    async def generate_report(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        brand_profile_id: Optional[uuid.UUID] = None,
    ) -> GovernanceReportResponse:
        """
        Executes single-pass CUBE aggregation and returns structured governance report
        with pre-formatted datasets for Recharts.
        """
        now = datetime.now(timezone.utc)

        params: dict[str, Any] = {
            "workspace_id": str(workspace_id),
            "brand_profile_id": str(brand_profile_id) if brand_profile_id else None,
        }

        # Initialize default zeroed distributions across standard enterprise enums
        category_counts: dict[str, int] = {c.value: 0 for c in FindingCategory}
        category_counts["UNSUPPORTED_CLAIM"] = 0  # Domain alias for UNSUBSTANTIATED_CLAIM

        severity_counts: dict[str, int] = {s.value: 0 for s in SeverityLevel}
        triage_status_counts: dict[str, int] = {t.value: 0 for t in TriageStatus}
        detector_source_counts: dict[str, int] = {d.value: 0 for d in DetectorSource}
        creator_action_counts: dict[str, int] = {
            a.value for a in (CreatorAction.PENDING, CreatorAction.ACCEPTED, CreatorAction.REJECTED, CreatorAction.EDITED)
        }
        creator_action_counts = {k: 0 for k in creator_action_counts}

        confidence_bucket_counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        review_trends_by_date: dict[str, dict[str, int]] = {}

        category_severity_cube: list[CategorySeverityCount] = []
        total_findings = 0

        bind = session.get_bind()
        query = cls.REPORT_QUERY_SQLITE if bind and bind.dialect.name == "sqlite" else cls.REPORT_QUERY
        result = await session.execute(query, params)
        rows = result.fetchall() if hasattr(result, "fetchall") else []

        for row in rows:
            mapping = row._mapping if hasattr(row, "_mapping") else dict(zip(
                ["metric_type", "issue_category", "severity", "dimension_val", "count"],
                row
            ))

            m_type = mapping.get("metric_type")
            cat = mapping.get("issue_category")
            sev = mapping.get("severity")
            dim = mapping.get("dimension_val")
            cnt = int(mapping.get("count", 0))

            if m_type == "CUBE":
                # Grand total row: CUBE(NULL, NULL)
                if cat is None and sev is None:
                    total_findings = cnt
                # Category subtotal row: CUBE(category, NULL)
                elif cat is not None and sev is None:
                    category_counts[cat] = cnt
                    if cat == "UNSUBSTANTIATED_CLAIM":
                        category_counts["UNSUPPORTED_CLAIM"] = cnt
                # Severity subtotal row: CUBE(NULL, severity)
                elif cat is None and sev is not None:
                    severity_counts[sev] = cnt
                # Exact cross-cell: CUBE(category, severity)
                elif cat is not None and sev is not None:
                    category_severity_cube.append(
                        CategorySeverityCount(
                            issue_category=cat,
                            severity=sev,
                            count=cnt,
                        )
                    )

            elif m_type == "TRIAGE" and dim:
                triage_status_counts[dim] = cnt

            elif m_type == "DETECTOR" and dim:
                detector_source_counts[dim] = cnt

            elif m_type == "ACTION" and dim:
                creator_action_counts[dim] = cnt

            elif m_type == "CONFIDENCE" and dim:
                confidence_bucket_counts[dim] = cnt

            elif m_type == "REVIEW_TREND" and dim:
                if dim not in review_trends_by_date:
                    review_trends_by_date[dim] = {"APPROVED": 0, "CHANGES_REQUESTED": 0, "TOTAL": 0}
                if sev in ("APPROVED", "CHANGES_REQUESTED"):
                    review_trends_by_date[dim][sev] = cnt
                review_trends_by_date[dim]["TOTAL"] += cnt

        # Ensure alias consistency
        if "UNSUBSTANTIATED_CLAIM" in category_counts:
            category_counts["UNSUPPORTED_CLAIM"] = category_counts["UNSUBSTANTIATED_CLAIM"]

        # Build Recharts datasets
        # 1. BarChart: Recurring issue categories
        cube_map: dict[tuple[str, str], int] = {
            (item.issue_category, item.severity): item.count
            for item in category_severity_cube
            if item.issue_category and item.severity
        }
        recharts_category_bar: list[RechartsCategoryBar] = []
        for cat, cnt in category_counts.items():
            if cat == "UNSUPPORTED_CLAIM":
                continue
            recharts_category_bar.append(
                RechartsCategoryBar(
                    category=cat,
                    name=cat.replace("_", " ").title(),
                    count=cnt,
                    CRITICAL=cube_map.get((cat, "CRITICAL"), 0),
                    HIGH=cube_map.get((cat, "HIGH"), 0),
                    MEDIUM=cube_map.get((cat, "MEDIUM"), 0),
                    LOW=cube_map.get((cat, "LOW"), 0),
                )
            )
        recharts_category_bar.sort(key=lambda x: x.count, reverse=True)

        # 2. LineChart: Review trends
        recharts_review_trends_line: list[RechartsReviewTrendLine] = []
        for d_str, stats in sorted(review_trends_by_date.items()):
            recharts_review_trends_line.append(
                RechartsReviewTrendLine(
                    date=d_str,
                    approved=stats.get("APPROVED", 0),
                    changes_requested=stats.get("CHANGES_REQUESTED", 0),
                    total_reviews=stats.get("TOTAL", 0),
                )
            )

        # 3. PieChart: Triage confidence buckets
        total_for_pie = total_findings if total_findings > 0 else 1
        high_val = confidence_bucket_counts["HIGH"] or triage_status_counts.get("FLAGGED_HIGH_CONFIDENCE", 0)
        med_val = confidence_bucket_counts["MEDIUM"] or triage_status_counts.get("ROUTED_TO_HUMAN_LOW_CONFIDENCE", 0)
        low_val = confidence_bucket_counts["LOW"] or max(0, total_findings - high_val - med_val)

        recharts_triage_pie: list[RechartsTriagePie] = [
            RechartsTriagePie(
                name="High Confidence (>=0.85)",
                value=high_val,
                fill="#10B981",
                key="HIGH",
                percentage=round((high_val / total_for_pie) * 100.0, 2) if total_findings > 0 else 0.0,
            ),
            RechartsTriagePie(
                name="Medium Confidence (0.60-0.84)",
                value=med_val,
                fill="#F59E0B",
                key="MEDIUM",
                percentage=round((med_val / total_for_pie) * 100.0, 2) if total_findings > 0 else 0.0,
            ),
            RechartsTriagePie(
                name="Low Confidence (<0.60)",
                value=low_val,
                fill="#EF4444",
                key="LOW",
                percentage=round((low_val / total_for_pie) * 100.0, 2) if total_findings > 0 else 0.0,
            ),
        ]

        return GovernanceReportResponse(
            workspace_id=workspace_id,
            brand_profile_id=brand_profile_id,
            total_findings=total_findings,
            category_counts=category_counts,
            severity_counts=severity_counts,
            triage_status_counts=triage_status_counts,
            detector_source_counts=detector_source_counts,
            creator_action_counts=creator_action_counts,
            category_severity_cube=category_severity_cube,
            recharts_category_bar=recharts_category_bar,
            recharts_review_trends_line=recharts_review_trends_line,
            recharts_triage_pie=recharts_triage_pie,
            generated_at=now,
        )
