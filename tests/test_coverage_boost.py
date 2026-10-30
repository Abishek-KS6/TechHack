"""
BrandShield AI - Coverage Boost Tests
Targets low-coverage modules:
  - FindingTriageService           (48% -> target 90%)
  - RetentionReaperService         (40% -> target 90%)
  - TraceabilityAuditService       (75% -> target 90%)
  - SubmissionService              (63% -> target 90%)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.enums import TriageStatus
from app.services.finding_triage_service import FindingTriageService


class TestFindingTriageClassify:
    def test_stale_fact_takes_precedence(self):
        status = FindingTriageService.classify_triage(0.99, True, True)
        assert status == TriageStatus.STALE_FACT_REVERIFY

    def test_missing_evidence_routes_to_verification(self):
        status = FindingTriageService.classify_triage(0.95, False, False)
        assert status == TriageStatus.NEEDS_VERIFICATION_MISSING_EVIDENCE

    def test_high_confidence_with_evidence_flagged(self):
        status = FindingTriageService.classify_triage(0.90, True, False)
        assert status == TriageStatus.FLAGGED_HIGH_CONFIDENCE

    def test_below_threshold_routes_to_human(self):
        status = FindingTriageService.classify_triage(0.89, True, False)
        assert status == TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE

    def test_zero_confidence_with_evidence(self):
        status = FindingTriageService.classify_triage(0.0, True, False)
        assert status == TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE


class TestFindingTriageIngestFinding:
    def _make_payload(self, revision_id, confidence=0.95, linked_fact_id=None):
        from app.domain.enums import DetectorSource, FindingCategory, SeverityLevel, TriageStatus
        from app.domain.schemas.finding import FindingCreate
        return FindingCreate(
            revision_id=revision_id,
            issue_category=FindingCategory.TONE,
            severity=SeverityLevel.HIGH,
            confidence_score=confidence,
            triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
            start_offset=0,
            end_offset=10,
            explanation_reason="Test explanation reason for finding",
            suggested_correction="Fix this issue please",
            detector_source=DetectorSource.DETERMINISTIC_RULE,
            linked_guideline_id=uuid.uuid4() if not linked_fact_id else None,
            linked_fact_id=linked_fact_id,
        )

    @pytest.mark.asyncio
    async def test_revision_not_found_raises(self):
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        payload = self._make_payload(uuid.uuid4())
        with pytest.raises(ValueError, match="does not exist"):
            await FindingTriageService.ingest_finding(session, payload, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_normal_path_no_audit(self):
        from app.infrastructure.db.models import DocumentRevision, Finding
        rev_id = uuid.uuid4()
        mock_rev = MagicMock(spec=DocumentRevision)
        mock_rev.id = rev_id
        session = AsyncMock()
        session.get = AsyncMock(return_value=mock_rev)
        session.add = MagicMock()
        session.flush = AsyncMock()
        payload = self._make_payload(rev_id, confidence=0.95)
        with patch("app.services.finding_triage_service.random.random", return_value=1.0):
            with patch("app.services.finding_triage_service.AuditService.record_event", new_callable=AsyncMock):
                result = await FindingTriageService.ingest_finding(session, payload, uuid.uuid4())
        assert isinstance(result, Finding)
        assert result.is_automation_bias_audit is False

    @pytest.mark.asyncio
    async def test_stochastic_audit_injected(self):
        from app.infrastructure.db.models import DocumentRevision, Finding
        rev_id = uuid.uuid4()
        mock_rev = MagicMock(spec=DocumentRevision)
        mock_rev.id = rev_id
        session = AsyncMock()
        session.get = AsyncMock(return_value=mock_rev)
        session.add = MagicMock()
        session.flush = AsyncMock()
        payload = self._make_payload(rev_id)
        with patch("app.services.finding_triage_service.random.random", return_value=0.0):
            with patch("app.services.finding_triage_service.AuditService.record_event", new_callable=AsyncMock) as mock_audit:
                result = await FindingTriageService.ingest_finding(session, payload, uuid.uuid4())
        assert result.is_automation_bias_audit is True
        mock_audit.assert_called_once()

    @pytest.mark.asyncio
    async def test_linked_stale_fact_sets_triage(self):
        from app.infrastructure.db.models import ApprovedFact, DocumentRevision
        rev_id = uuid.uuid4()
        fact_id = uuid.uuid4()
        mock_rev = MagicMock(spec=DocumentRevision)
        mock_rev.id = rev_id
        mock_fact = MagicMock(spec=ApprovedFact)
        mock_fact.expiry_date = datetime.now(timezone.utc) - timedelta(days=1)
        session = AsyncMock()
        call_count = [0]
        async def side_get(model, pk):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_rev
            return mock_fact
        session.get.side_effect = side_get
        session.add = MagicMock()
        session.flush = AsyncMock()
        payload = self._make_payload(rev_id, linked_fact_id=fact_id)
        with patch("app.services.finding_triage_service.random.random", return_value=1.0):
            with patch("app.services.finding_triage_service.AuditService.record_event", new_callable=AsyncMock):
                result = await FindingTriageService.ingest_finding(session, payload, uuid.uuid4())
        assert result.triage_status == TriageStatus.STALE_FACT_REVERIFY

    @pytest.mark.asyncio
    async def test_update_creator_action_not_found_raises(self):
        from app.domain.enums import CreatorAction
        from app.domain.schemas.finding import FindingUpdateAction
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        payload = FindingUpdateAction(creator_action=CreatorAction.ACCEPTED, creator_comment="OK")
        with pytest.raises(ValueError, match="does not exist"):
            await FindingTriageService.update_creator_action(session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_update_creator_action_happy_path(self):
        from app.domain.enums import CreatorAction
        from app.domain.schemas.finding import FindingUpdateAction
        from app.infrastructure.db.models import Finding
        mock_finding = MagicMock(spec=Finding)
        mock_finding.id = uuid.uuid4()
        mock_finding.revision_id = uuid.uuid4()
        session = AsyncMock()
        session.get = AsyncMock(return_value=mock_finding)
        session.flush = AsyncMock()
        payload = FindingUpdateAction(creator_action=CreatorAction.ACCEPTED, creator_comment="Good")
        with patch("app.services.finding_triage_service.AuditService.record_event", new_callable=AsyncMock) as mock_audit:
            result = await FindingTriageService.update_creator_action(session, mock_finding.id, uuid.uuid4(), uuid.uuid4(), payload)
        assert result is mock_finding
        assert mock_finding.creator_action == CreatorAction.ACCEPTED
        mock_audit.assert_called_once()


from app.services.governance.retention_reaper import PURGED_PLACEHOLDER, RetentionReaperResult, RetentionReaperService


def _make_sub(days_old=60, retention_days=30, revisions=None):
    sub = MagicMock()
    sub.id = uuid.uuid4()
    sub.workspace_id = uuid.uuid4()
    sub.creator_id = uuid.uuid4()
    sub.brand_profile = MagicMock()
    sub.brand_profile.privacy_gate_config = {"retention_days": retention_days}
    sub.created_at = datetime.now(timezone.utc) - timedelta(days=days_old)
    sub.revisions = revisions or []
    return sub


class TestRetentionReaperResult:
    def test_to_dict(self):
        r = RetentionReaperResult(2, 4, 10, "ts", False, ["a", "b"])
        d = r.to_dict()
        assert d["purged_submissions_count"] == 2
        assert "a" in d["purged_submission_ids"]


class TestRetentionReaper:
    def _empty_session(self):
        session = AsyncMock()
        mr = MagicMock()
        mr.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mr)
        return session

    @pytest.mark.asyncio
    async def test_no_submissions(self):
        result = await RetentionReaperService.enforce_retention(session=self._empty_session())
        assert result.purged_submissions_count == 0

    @pytest.mark.asyncio
    async def test_recent_not_purged(self):
        recent = _make_sub(days_old=5, retention_days=30)
        session = AsyncMock()
        mr = MagicMock(); mr.scalars.return_value.all.return_value = [recent]
        session.execute = AsyncMock(return_value=mr)
        result = await RetentionReaperService.enforce_retention(session=session)
        assert result.purged_submissions_count == 0

    @pytest.mark.asyncio
    async def test_dry_run_does_not_mutate(self):
        rev = MagicMock(); rev.content_text = "Original"
        old = _make_sub(days_old=90, revisions=[rev])
        session = AsyncMock()
        mr = MagicMock(); mr.scalars.return_value.all.return_value = [old]
        fr = MagicMock(); fr.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[mr, fr])
        result = await RetentionReaperService.enforce_retention(session=session, dry_run=True)
        assert result.purged_submissions_count == 1
        assert rev.content_text == "Original"

    @pytest.mark.asyncio
    async def test_live_run_mutates_content(self):
        rev = MagicMock(); rev.id = uuid.uuid4(); rev.content_text = "Sensitive"
        old = _make_sub(days_old=90, revisions=[rev])
        session = AsyncMock()
        mr = MagicMock(); mr.scalars.return_value.all.return_value = [old]
        fr = MagicMock(); fr.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[mr, fr])
        session.commit = AsyncMock()
        with patch("app.services.governance.retention_reaper.AuditService.record_event", new_callable=AsyncMock):
            result = await RetentionReaperService.enforce_retention(session=session, dry_run=False)
        assert rev.content_text == PURGED_PLACEHOLDER
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_already_purged_not_counted(self):
        rev = MagicMock(); rev.id = uuid.uuid4(); rev.content_text = PURGED_PLACEHOLDER
        old = _make_sub(days_old=90, revisions=[rev])
        session = AsyncMock()
        mr = MagicMock(); mr.scalars.return_value.all.return_value = [old]
        fr = MagicMock(); fr.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[mr, fr])
        session.commit = AsyncMock()
        with patch("app.services.governance.retention_reaper.AuditService.record_event", new_callable=AsyncMock):
            result = await RetentionReaperService.enforce_retention(session=session, dry_run=False)
        assert result.purged_revisions_count == 0

    @pytest.mark.asyncio
    async def test_forced_retention_days(self):
        rev = MagicMock(); rev.id = uuid.uuid4(); rev.content_text = "Data"
        sub = _make_sub(days_old=10, retention_days=30, revisions=[rev])
        session = AsyncMock()
        mr = MagicMock(); mr.scalars.return_value.all.return_value = [sub]
        fr = MagicMock(); fr.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[mr, fr])
        session.commit = AsyncMock()
        with patch("app.services.governance.retention_reaper.AuditService.record_event", new_callable=AsyncMock):
            result = await RetentionReaperService.enforce_retention(session=session, forced_retention_days=5, dry_run=False)
        assert result.purged_submissions_count == 1

    @pytest.mark.asyncio
    async def test_no_brand_profile_defaults_30_days(self):
        rev = MagicMock(); rev.id = uuid.uuid4(); rev.content_text = "Data"
        sub = MagicMock()
        sub.id = uuid.uuid4(); sub.workspace_id = uuid.uuid4(); sub.creator_id = uuid.uuid4()
        sub.brand_profile = None
        sub.created_at = datetime.now(timezone.utc) - timedelta(days=60)
        sub.revisions = [rev]
        session = AsyncMock()
        mr = MagicMock(); mr.scalars.return_value.all.return_value = [sub]
        fr = MagicMock(); fr.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[mr, fr])
        session.commit = AsyncMock()
        with patch("app.services.governance.retention_reaper.AuditService.record_event", new_callable=AsyncMock):
            result = await RetentionReaperService.enforce_retention(session=session, dry_run=False)
        assert result.purged_submissions_count == 1


from app.services.submission_service import SubmissionService


class TestSubmissionServiceStatic:
    def test_sha256_deterministic(self):
        assert SubmissionService.calculate_sha256("x") == SubmissionService.calculate_sha256("x")
        assert len(SubmissionService.calculate_sha256("x")) == 64

    def test_sha256_different_inputs(self):
        assert SubmissionService.calculate_sha256("a") != SubmissionService.calculate_sha256("b")

    def test_diff_addition(self):
        d = SubmissionService.compute_diff("line1\n", "line1\nline2\n")
        assert d["lines_added"] >= 1
        assert d["lines_removed"] == 0

    def test_diff_removal(self):
        d = SubmissionService.compute_diff("line1\nline2\n", "line1\n")
        assert d["lines_added"] == 0
        assert d["lines_removed"] >= 1

    def test_diff_identical(self):
        d = SubmissionService.compute_diff("same\n", "same\n")
        assert d["lines_added"] == 0
        assert d["lines_removed"] == 0


class TestSubmissionServiceAsync:
    @pytest.mark.asyncio
    async def test_create_submission_happy_path(self):
        from app.domain.schemas.submission import SubmissionCreate
        from app.infrastructure.db.models import Submission
        payload = SubmissionCreate(
            workspace_id=uuid.uuid4(), brand_profile_id=uuid.uuid4(),
            title="Doc", document_type="TEXT", initial_content="Hello", ast_span_map=[]
        )
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        with patch("app.services.submission_service.AuditService.record_event", new_callable=AsyncMock):
            result = await SubmissionService.create_submission(session, payload, uuid.uuid4())
        assert isinstance(result, Submission)
        assert result.title == "Doc"

    @pytest.mark.asyncio
    async def test_commit_revision_not_found(self):
        session = AsyncMock()
        qr = MagicMock(); qr.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=qr)
        with pytest.raises(ValueError, match="does not exist"):
            await SubmissionService.commit_revision(session, uuid.uuid4(), "new", [], uuid.uuid4())

    @pytest.mark.asyncio
    async def test_commit_revision_no_head(self):
        from app.infrastructure.db.models import Submission
        mock_sub = MagicMock(spec=Submission)
        mock_sub.id = uuid.uuid4()
        mock_sub.current_revision = None
        session = AsyncMock()
        qr = MagicMock(); qr.scalar_one_or_none.return_value = mock_sub
        session.execute = AsyncMock(return_value=qr)
        with pytest.raises(ValueError, match="no valid head revision"):
            await SubmissionService.commit_revision(session, mock_sub.id, "new", [], uuid.uuid4())

    @pytest.mark.asyncio
    async def test_commit_revision_happy_path(self):
        from app.domain.enums import WorkflowState
        from app.infrastructure.db.models import DocumentRevision, Submission
        parent = MagicMock(spec=DocumentRevision)
        parent.id = uuid.uuid4(); parent.revision_number = 1
        parent.content_text = "Old"
        parent.get_decrypted_content = MagicMock(return_value="Old")
        mock_sub = MagicMock(spec=Submission)
        mock_sub.id = uuid.uuid4(); mock_sub.workspace_id = uuid.uuid4()
        mock_sub.current_revision = parent
        session = AsyncMock()
        qr = MagicMock(); qr.scalar_one_or_none.return_value = mock_sub
        session.execute = AsyncMock(return_value=qr)
        session.add = MagicMock(); session.flush = AsyncMock()
        with patch("app.services.submission_service.AuditService.record_event", new_callable=AsyncMock):
            result = await SubmissionService.commit_revision(session, mock_sub.id, "New content", [], uuid.uuid4())
        assert isinstance(result, DocumentRevision)
        assert result.revision_number == 2
        assert mock_sub.workflow_state == WorkflowState.ANALYZING

    @pytest.mark.asyncio
    async def test_review_not_found_raises(self):
        from app.domain.enums import ReviewSignOff
        from app.domain.schemas.submission import ReviewDecisionCreate
        session = AsyncMock(); session.get = AsyncMock(return_value=None)
        payload = ReviewDecisionCreate(decision=ReviewSignOff.APPROVED, comments="Looks good to me")
        with pytest.raises(ValueError, match="does not exist"):
            await SubmissionService.record_review_decision(session, uuid.uuid4(), uuid.uuid4(), payload)

    @pytest.mark.asyncio
    async def test_review_approved_transitions(self):
        from app.domain.enums import ReviewSignOff, WorkflowState
        from app.domain.schemas.submission import ReviewDecisionCreate
        from app.infrastructure.db.models import ReviewDecision, Submission
        mock_sub = MagicMock(spec=Submission)
        mock_sub.id = uuid.uuid4(); mock_sub.workspace_id = uuid.uuid4()
        mock_sub.current_revision_id = uuid.uuid4()
        session = AsyncMock(); session.get = AsyncMock(return_value=mock_sub)
        session.add = MagicMock(); session.flush = AsyncMock()
        payload = ReviewDecisionCreate(decision=ReviewSignOff.APPROVED, comments="All good")
        with patch("app.services.submission_service.AuditService.record_event", new_callable=AsyncMock):
            result = await SubmissionService.record_review_decision(session, mock_sub.id, uuid.uuid4(), payload)
        assert isinstance(result, ReviewDecision)
        assert mock_sub.workflow_state == WorkflowState.APPROVED

    @pytest.mark.asyncio
    async def test_review_changes_requested_transitions(self):
        from app.domain.enums import ReviewSignOff, WorkflowState
        from app.domain.schemas.submission import ReviewDecisionCreate
        from app.infrastructure.db.models import Submission
        mock_sub = MagicMock(spec=Submission)
        mock_sub.id = uuid.uuid4(); mock_sub.workspace_id = uuid.uuid4()
        mock_sub.current_revision_id = uuid.uuid4()
        session = AsyncMock(); session.get = AsyncMock(return_value=mock_sub)
        session.add = MagicMock(); session.flush = AsyncMock()
        payload = ReviewDecisionCreate(decision=ReviewSignOff.CHANGES_REQUESTED, comments="Fix it")
        with patch("app.services.submission_service.AuditService.record_event", new_callable=AsyncMock):
            await SubmissionService.record_review_decision(session, mock_sub.id, uuid.uuid4(), payload)
        assert mock_sub.workflow_state == WorkflowState.CHANGES_REQUESTED


from app.services.governance.traceability_service import TraceabilityAuditService


class TestTraceabilityAuditService:
    def _session_with(self, row_values=None):
        session = AsyncMock()
        if row_values is None:
            result = MagicMock(); result.fetchone.return_value = None
        else:
            row = MagicMock(); row._mapping = row_values
            result = MagicMock(); result.fetchone.return_value = row
        session.execute = AsyncMock(return_value=result)
        return session

    @pytest.mark.asyncio
    async def test_zero_findings_100pct(self):
        result = await TraceabilityAuditService.compute_metrics(self._session_with(None), uuid.uuid4())
        assert result.traceability_percentage == 100.0
        assert result.is_zero_ungrounded_verified is True

    @pytest.mark.asyncio
    async def test_all_grounded(self):
        result = await TraceabilityAuditService.compute_metrics(
            self._session_with({"total_findings": 10, "grounded_findings_count": 10,
                                "ungrounded_findings_count": 0, "guideline_linked_count": 8,
                                "fact_linked_count": 2, "both_linked_count": 0,
                                "unsubstantiated_claims_count": 0}),
            uuid.uuid4())
        assert result.traceability_percentage == 100.0
        assert result.is_zero_ungrounded_verified is True

    @pytest.mark.asyncio
    async def test_partial_traceability(self):
        result = await TraceabilityAuditService.compute_metrics(
            self._session_with({"total_findings": 4, "grounded_findings_count": 3,
                                "ungrounded_findings_count": 1, "guideline_linked_count": 2,
                                "fact_linked_count": 1, "both_linked_count": 0,
                                "unsubstantiated_claims_count": 0}),
            uuid.uuid4())
        assert result.traceability_percentage == 75.0
        assert result.is_zero_ungrounded_verified is False

    @pytest.mark.asyncio
    async def test_brand_profile_id_forwarded(self):
        brand_id = uuid.uuid4()
        result = await TraceabilityAuditService.compute_metrics(
            self._session_with(None), uuid.uuid4(), brand_profile_id=brand_id)
        assert result.brand_profile_id == brand_id

    @pytest.mark.asyncio
    async def test_audit_timestamp_recent(self):
        before = datetime.now(timezone.utc)
        result = await TraceabilityAuditService.compute_metrics(self._session_with(None), uuid.uuid4())
        after = datetime.now(timezone.utc)
        assert before <= result.audit_timestamp <= after

