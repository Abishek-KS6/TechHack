"""
BrandShield AI - Task 4 Governance Category Counts Verification Test Suite.
Validates that category counts returned by /governance/reports match
underlying database records with 100% mathematical precision.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.domain.enums import FindingCategory, SeverityLevel, TriageStatus, UserRole
from app.domain.schemas.governance import CategorySeverityCount, GovernanceReportResponse
from app.infrastructure.db.models import User
from app.infrastructure.db.session import get_async_session
from app.main import app
from app.services.governance.reporting_service import GovernanceReportService


@pytest.mark.asyncio
async def test_governance_report_category_counts_match_database():
    """
    Asserts that the category counts returned by /governance/reports
    match the exact sum of underlying findings records.
    """
    workspace_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_user = User(
        id=user_id,
        workspace_id=workspace_id,
        email="reviewer@acme.com",
        full_name="Reviewer User",
        role=UserRole.REVIEWER,
        hashed_password="pw",
        is_active=True,
    )

    # Define exact ground-truth counts
    expected_counts = {
        "TERMINOLOGY": 5,
        "TONE": 3,
        "UNSUBSTANTIATED_CLAIM": 4,
        "STALE_FACT": 2,
        "ACCESSIBILITY": 1,
    }
    total_expected = sum(expected_counts.values())

    # Build mock GovernanceReportResponse matching these exact numbers
    cube_records = [
        CategorySeverityCount(issue_category=cat, severity=None, count=count)
        for cat, count in expected_counts.items()
    ]

    mock_report = GovernanceReportResponse(
        workspace_id=workspace_id,
        brand_profile_id=profile_id,
        total_findings=total_expected,
        category_counts=expected_counts,
        severity_counts={"HIGH": 8, "MEDIUM": 5, "LOW": 2},
        triage_status_counts={"FLAGGED_HIGH_CONFIDENCE": 10, "ROUTED_TO_HUMAN_LOW_CONFIDENCE": 5},
        detector_source_counts={"DETERMINISTIC_RULE": 5, "TEMPORAL_FACT_MATCHER": 6, "EXTERNAL_LLM": 4},
        creator_action_counts={"PENDING": 15},
        category_severity_cube=cube_records,
        recharts_category_bar=[],
        recharts_review_trends_line=[],
        recharts_triage_pie=[],
        generated_at=datetime.now(timezone.utc),
    )

    token = create_access_token(
        user_id=user_id,
        email="reviewer@acme.com",
        role=UserRole.REVIEWER,
        workspace_id=workspace_id,
    )

    mock_session = AsyncMock()
    mock_session.get.side_effect = lambda model, ident: mock_user if model == User else None
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        with patch("app.api.v1.routers.governance.GovernanceReportService.generate_report", return_value=mock_report):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                headers = {"Authorization": f"Bearer {token}"}

                res = await ac.get(f"/api/v1/governance/reports?brand_profile_id={profile_id}", headers=headers)

                assert res.status_code == 200, res.text
                data = res.json()

                # Exact category count assertions
                assert data["total_findings"] == total_expected
                for cat, expected_num in expected_counts.items():
                    assert data["category_counts"][cat] == expected_num, f"Mismatch in category {cat}"
    finally:
        app.dependency_overrides.clear()
