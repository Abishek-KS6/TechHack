"""
BrandShield AI - Task 1 Evidence-Linked Findings Test Suite.
Validates:
1. Every finding from /api/v1/analysis/live includes plain-language reason, severity, and evidence source/link.
2. Findings without supporting evidence have status NEEDS_VERIFICATION.
3. Tests all three calibrated outcomes: FLAGGED_HIGH_CONFIDENCE, ROUTED_TO_HUMAN_LOW_CONFIDENCE, NEEDS_VERIFICATION.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.domain.enums import FindingCategory, GuidelineCategory, SeverityLevel, TriageStatus, UserRole
from app.domain.schemas.analysis import AdHocFinding
from app.infrastructure.db.models import BrandGuideline, BrandProfile, User, Workspace
from app.infrastructure.db.session import get_async_session
from app.main import app
from app.services.analysis.deterministic_engine import BrandAutomatonCache
from app.services.analysis.privacy_gate import ToneAnalysisFinding


@pytest.mark.asyncio
async def test_live_analysis_evidence_link_and_three_triage_outcomes():
    """
    Asserts:
    1. Deterministic finding with guideline link -> FLAGGED_HIGH_CONFIDENCE + evidence citation.
    2. Tone finding with link & low confidence (<0.85) -> ROUTED_TO_HUMAN_LOW_CONFIDENCE.
    3. Tone finding without link -> NEEDS_VERIFICATION.
    """
    workspace_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    guideline_id = uuid.uuid4()

    mock_profile = BrandProfile(
        id=profile_id,
        workspace_id=workspace_id,
        name="Acme Corp",
        banned_terminology_map={"foolproof": {"reason": "Prohibited guarantee term", "severity": "HIGH"}},
        preferred_terminology_map={},
        tone_parameters={"formality": 8.0},
        privacy_gate_config={"allow_external_llm": True, "contract_verified_at": "2026-01-01T00:00:00Z", "retention_days": 14, "approved_providers": ["Azure OpenAI"]},
    )

    # Tone hit with valid guideline link and low confidence (0.70) -> human review
    mock_tone_hit_low = ToneAnalysisFinding(
        issue_category=FindingCategory.TONE,
        severity=SeverityLevel.MEDIUM,
        confidence_score=0.70,
        triage_status=TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE,
        start_offset=10,
        end_offset=25,
        explanation_reason="Tone formality deviates from corporate threshold.",
        suggested_correction="Maintain executive tone.",
        detector_source="EXTERNAL_LLM",
        linked_guideline_id=guideline_id,
    )

    # Tone hit with no supporting evidence -> NEEDS_VERIFICATION
    mock_tone_hit_no_evidence = ToneAnalysisFinding(
        issue_category=FindingCategory.TONE,
        severity=SeverityLevel.LOW,
        confidence_score=0.90,
        triage_status=TriageStatus.NEEDS_VERIFICATION,
        start_offset=30,
        end_offset=45,
        explanation_reason="Ambiguous style nuance without cited guideline rule.",
        suggested_correction=None,
        detector_source="EXTERNAL_LLM",
        linked_guideline_id=None,
        linked_fact_id=None,
    )

    user_id = uuid.uuid4()
    mock_user = User(
        id=user_id,
        workspace_id=workspace_id,
        email="creator@acme.com",
        full_name="Creator User",
        role=UserRole.CREATOR,
        hashed_password="pw",
        is_active=True,
    )

    token = create_access_token(
        user_id=user_id,
        email="creator@acme.com",
        role=UserRole.CREATOR,
        workspace_id=workspace_id,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return mock_user
        if model == BrandProfile:
            return mock_profile
        return None

    mock_session.get.side_effect = mock_get
    BrandAutomatonCache.clear()
    mock_guideline = BrandGuideline(
        id=guideline_id,
        brand_profile_id=profile_id,
        clause_identifier="TERM-01",
        clause_text="Prohibited Terminology",
        category=GuidelineCategory.TERMINOLOGY,
        severity=SeverityLevel.HIGH,
        embedding=[0.0] * 1536,
        is_active=True,
    )

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [mock_guideline]
    mock_session.execute.return_value = mock_res
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        with patch("app.api.v1.routers.analysis.PrivacyGateRouter.analyze_tone_and_messaging", return_value=[mock_tone_hit_low, mock_tone_hit_no_evidence]), \
             patch("app.api.v1.routers.analysis.TemporalFactEngine.evaluate_claims", return_value=[]):

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                headers = {"Authorization": f"Bearer {token}"}

                response = await ac.post(
                    "/api/v1/analysis/live",
                    json={
                        "content_text": "Our foolproof platform is kinda informal and very innovative.",
                        "brand_profile_id": str(profile_id),
                        "requested_provider": "Azure OpenAI",
                    },
                    headers=headers,
                )

                assert response.status_code == 200, response.text
                data = response.json()
                findings = data["findings"]
                assert len(findings) >= 3

                # Check triage statuses
                statuses = [f["triage_status"] for f in findings]
                assert TriageStatus.FLAGGED_HIGH_CONFIDENCE in statuses
                assert TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE in statuses
                assert TriageStatus.NEEDS_VERIFICATION in statuses

                # Verify every finding has plain-language reason, severity, and evidence fields
                for f in findings:
                    assert len(f["explanation_reason"]) >= 5
                    assert f["severity"] in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
                    assert "evidence_source" in f
                    assert "evidence_link" in f
    finally:
        app.dependency_overrides.clear()
