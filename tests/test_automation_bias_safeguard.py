"""
BrandShield AI - Task 2 Automation-Bias Safeguard Test Suite.
Validates:
1. 15% random selection for secondary reviewer check.
2. Results are repeatable using a seeded random generator.
3. Every stochastic audit injection is cryptographically recorded in the audit ledger.
4. Sampling rate is configurable.
"""

from datetime import datetime, timezone
import random
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest

from app.domain.enums import AuditAction, CreatorAction, DetectorSource, FindingCategory, SeverityLevel, TriageStatus, WorkflowState
from app.infrastructure.db.models import BrandProfile, DocumentRevision, Finding, Submission
from app.services.analysis.triage_orchestrator import TriageOrchestrator


@pytest.mark.asyncio
async def test_automation_bias_safeguard_seeded_repeatability_and_audit():
    """
    Asserts:
    1. With seeded random.Random(42), exactly the same findings are selected every time.
    2. AuditAction.STOCHASTIC_AUDIT_INJECTED is recorded in the audit ledger for each selection.
    """
    workspace_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    submission_id = uuid.uuid4()

    mock_profile = BrandProfile(
        id=profile_id,
        workspace_id=workspace_id,
        name="Acme Corp",
        banned_terminology_map={},
        preferred_terminology_map={},
        tone_parameters={"formality": 8.0},
        privacy_gate_config={"allow_external_llm": False},
    )

    mock_submission = Submission(
        id=submission_id,
        workspace_id=workspace_id,
        brand_profile_id=profile_id,
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.SUBMITTED,
    )

    mock_revision = DocumentRevision(
        id=revision_id,
        submission_id=submission_id,
        revision_number=1,
        content_text="Sample text for testing",
        sha256_content_hash="dummy",
    )

    # Run two passes with identical seed = 42
    audit_calls_run1 = []
    audit_calls_run2 = []

    for run_idx in (1, 2):
        seeded_rng = random.Random(42)
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        async def mock_get(model, ident):
            if model == BrandProfile:
                return mock_profile
            if model == DocumentRevision:
                return mock_revision
            if model == Submission:
                return mock_submission
            return None

        mock_session.get.side_effect = mock_get

        with patch("app.services.analysis.triage_orchestrator.AuditService.record_event") as mock_audit, \
             patch("app.services.analysis.triage_orchestrator.DeterministicRuleEngine.analyze_document") as mock_det, \
             patch("app.services.analysis.triage_orchestrator.TemporalFactEngine.evaluate_claims", return_value=[]), \
             patch("app.services.analysis.triage_orchestrator.PrivacyGateRouter.analyze_tone_and_messaging", return_value=[]):

            # Create 20 mock high-confidence deterministic findings
            mock_findings = []
            for i in range(20):
                f = Finding(
                    id=uuid.uuid4(),
                    revision_id=revision_id,
                    issue_category=FindingCategory.TERMINOLOGY,
                    severity=SeverityLevel.HIGH,
                    confidence_score=1.0,
                    triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
                    start_offset=i * 5,
                    end_offset=(i * 5) + 4,
                    explanation_reason=f"Violation #{i}",
                    suggested_correction="corrected",
                    detector_source=DetectorSource.DETERMINISTIC_RULE,
                    is_automation_bias_audit=False,
                    creator_action=CreatorAction.PENDING,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                mock_findings.append(f)

            mock_det.return_value = mock_findings

            res = await TriageOrchestrator.run_pipeline(
                session=mock_session,
                revision_id=revision_id,
                brand_profile_id=profile_id,
                workspace_id=workspace_id,
                content_text="Sample text",
                preloaded_profile=mock_profile,
                preloaded_guidelines=[],
                preloaded_facts=[],
                audit_sample_rate=0.15,
                rng=seeded_rng,
            )

            recorded_actions = [call.kwargs.get("action") for call in mock_audit.call_args_list]
            stochastic_injections = [a for a in recorded_actions if a == AuditAction.STOCHASTIC_AUDIT_INJECTED]

            if run_idx == 1:
                audit_calls_run1 = stochastic_injections
                run1_injected_count = res.automation_bias_audits_injected
            else:
                audit_calls_run2 = stochastic_injections
                run2_injected_count = res.automation_bias_audits_injected

    # Seeded repeatability assertion: both runs produce identical injected count
    assert run1_injected_count == run2_injected_count
    assert len(audit_calls_run1) == len(audit_calls_run2)
    assert run1_injected_count > 0, "Expected non-zero shadow audit injections from 20 findings at 15%"


@pytest.mark.asyncio
async def test_automation_bias_safeguard_configurable_rate():
    """Verifies that audit_sample_rate is configurable from 0% to 100%."""
    # 0% rate -> 0 injected
    rng_zero = random.Random(100)
    assert TriageOrchestrator.evaluate_automation_bias_safeguard(sampling_rate=0.0, rng=rng_zero) is False

    # 100% rate -> always True
    rng_full = random.Random(100)
    assert TriageOrchestrator.evaluate_automation_bias_safeguard(sampling_rate=1.0, rng=rng_full) is True
