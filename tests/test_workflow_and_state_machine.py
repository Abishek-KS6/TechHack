"""
BrandShield AI - Human Review Workflow, Revision Engine & State Machine Test Suite.
Validates:
1. Strict Finite State Machine (FSM): legal transitions, terminal states, and strict AI/Creator approval bans.
2. Creator Suggestion Resolution (POST /submissions/{id}/findings/{finding_id}/resolve):
   ACCEPT, REJECT, EDIT, immutable DAG revision increment, AST offset recalculation, difflib patch, audit ledger.
3. Human Reviewer Sign-Off (POST /submissions/{id}/review):
   Reviewer governance, inline annotations, mandatory automation-bias safeguard audit verification, APPROVED/CHANGES_REQUESTED.
4. Revision Lineage & Side-by-Side Token Diff (GET /submissions/{id}/revisions/diff):
   Lineage DAG, unified line diffs, and exact side-by-side token diff chunks.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid
from httpx import ASGITransport, AsyncClient
import pytest

from app.core.security import create_access_token

from app.core.exceptions import (
    ForbiddenProblem,
    StateTransitionConflictProblem,
    ValidationErrorProblem,
)
from app.domain.enums import (
    AuditAction,
    CreatorAction,
    DetectorSource,
    FindingCategory,
    ReviewSignOff,
    SeverityLevel,
    TriageStatus,
    UserRole,
    WorkflowState,
)
from app.domain.schemas.submission import (
    FindingResolutionRequest,
    FindingVerificationInput,
    InlineCommentInput,
    ReviewSubmissionRequest,
)
from app.domain.state_machine import SubmissionStateMachine
from app.infrastructure.db.models import (
    DocumentRevision,
    Finding,
    Submission,
    User,
)
from app.infrastructure.db.session import get_async_session
from app.main import app
from app.services.workflow.diff_service import DiffService
from app.services.workflow.review_service import WorkflowReviewService
from app.services.workflow.revision_engine import RevisionEngine


@pytest.fixture
def workspace_id():
    return uuid.uuid4()


@pytest.fixture
def creator_user(workspace_id):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        email="author@brandshield.ai",
        hashed_password="argon2_hash_placeholder",
        full_name="Creative Author",
        role=UserRole.CREATOR,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def reviewer_user(workspace_id):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        email="compliance.reviewer@brandshield.ai",
        hashed_password="argon2_hash_placeholder",
        full_name="Compliance Officer",
        role=UserRole.REVIEWER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def admin_user(workspace_id):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        email="admin@brandshield.ai",
        hashed_password="argon2_hash_placeholder",
        full_name="Enterprise Admin",
        role=UserRole.ADMINISTRATOR,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def creator_token(creator_user):
    return create_access_token(
        user_id=creator_user.id,
        email=creator_user.email,
        role=creator_user.role,
        workspace_id=creator_user.workspace_id,
    )


@pytest.fixture
def reviewer_token(reviewer_user):
    return create_access_token(
        user_id=reviewer_user.id,
        email=reviewer_user.email,
        role=reviewer_user.role,
        workspace_id=reviewer_user.workspace_id,
    )


@pytest.fixture
def admin_token(admin_user):
    return create_access_token(
        user_id=admin_user.id,
        email=admin_user.email,
        role=admin_user.role,
        workspace_id=admin_user.workspace_id,
    )


# ==============================================================================
# 1. Finite State Machine Tests
# ==============================================================================

def test_fsm_valid_transition_sequence():
    """Validates the standard forward progression through the lifecycle states."""
    sub = Submission(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        brand_profile_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.SUBMITTED,
    )

    # SUBMITTED -> TRIAGED
    state = SubmissionStateMachine.transition(sub, WorkflowState.TRIAGED)
    assert state == WorkflowState.TRIAGED
    assert sub.workflow_state == WorkflowState.TRIAGED

    # TRIAGED -> IN_CREATOR_REVISION
    state = SubmissionStateMachine.transition(sub, WorkflowState.IN_CREATOR_REVISION, actor_role=UserRole.CREATOR)
    assert state == WorkflowState.IN_CREATOR_REVISION

    # IN_CREATOR_REVISION -> IN_HUMAN_REVIEW
    state = SubmissionStateMachine.transition(sub, WorkflowState.IN_HUMAN_REVIEW, actor_role=UserRole.CREATOR)
    assert state == WorkflowState.IN_HUMAN_REVIEW

    # IN_HUMAN_REVIEW -> APPROVED (by Reviewer)
    state = SubmissionStateMachine.transition(sub, WorkflowState.APPROVED, actor_role=UserRole.REVIEWER)
    assert state == WorkflowState.APPROVED


def test_fsm_changes_requested_loop():
    """Validates iterative feedback loop: REVIEW -> CHANGES_REQUESTED -> REVISION -> REVIEW."""
    sub = Submission(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        brand_profile_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.IN_HUMAN_REVIEW,
    )

    # Reviewer requests changes
    state = SubmissionStateMachine.transition(sub, WorkflowState.CHANGES_REQUESTED, actor_role=UserRole.REVIEWER)
    assert state == WorkflowState.CHANGES_REQUESTED

    # Creator re-enters revision
    state = SubmissionStateMachine.transition(sub, WorkflowState.IN_CREATOR_REVISION, actor_role=UserRole.CREATOR)
    assert state == WorkflowState.IN_CREATOR_REVISION

    # Creator submits again
    state = SubmissionStateMachine.transition(sub, WorkflowState.IN_HUMAN_REVIEW, actor_role=UserRole.CREATOR)
    assert state == WorkflowState.IN_HUMAN_REVIEW


def test_fsm_illegal_transitions_raise_409():
    """Validates that disconnected or reverse edge transitions raise StateTransitionConflictProblem."""
    sub = Submission(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        brand_profile_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.SUBMITTED,
    )

    # Cannot skip directly from SUBMITTED to APPROVED
    with pytest.raises(StateTransitionConflictProblem) as exc_info:
        SubmissionStateMachine.transition(sub, WorkflowState.APPROVED, actor_role=UserRole.REVIEWER)
    assert exc_info.value.status_code == 409
    assert "Illegal workflow transition" in exc_info.value.detail

    # Approved is a terminal state; cannot transition back to IN_CREATOR_REVISION
    sub.workflow_state = WorkflowState.APPROVED
    with pytest.raises(StateTransitionConflictProblem):
        SubmissionStateMachine.transition(sub, WorkflowState.IN_CREATOR_REVISION, actor_role=UserRole.CREATOR)


def test_fsm_ai_strictly_prohibited_from_approving():
    """
    CRITICAL ENTERPRISE GUARANTEE:
    AI or automated algorithms can NEVER transition a document to APPROVED.
    """
    sub = Submission(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        brand_profile_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.IN_HUMAN_REVIEW,
    )

    # Attempting approval with is_ai=True
    with pytest.raises(ForbiddenProblem) as exc_info:
        SubmissionStateMachine.transition(
            sub,
            WorkflowState.APPROVED,
            actor_role=UserRole.REVIEWER,
            is_ai=True,
        )
    assert exc_info.value.status_code == 403
    assert "Automated AI algorithms are strictly prohibited" in exc_info.value.detail


def test_fsm_creator_cannot_approve_submission():
    """Validates that a Creator cannot self-approve their own submission."""
    sub = Submission(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        brand_profile_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.IN_HUMAN_REVIEW,
    )

    with pytest.raises(ForbiddenProblem) as exc_info:
        SubmissionStateMachine.transition(sub, WorkflowState.APPROVED, actor_role=UserRole.CREATOR)
    assert exc_info.value.status_code == 403
    assert "Final approval requires certified compliance authorization" in exc_info.value.detail


# ==============================================================================
# 2. Creator Suggestion Resolution Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_resolve_finding_accept_creates_new_revision(creator_user):
    """
    Validates ACCEPT resolution:
    - Never overwrites parent content text.
    - Appends DocumentRevision v2 linked via parent_revision_id.
    - Recalculates AST character offsets.
    - Generates unified diff against parent.
    - Updates finding status to ACCEPTED.
    - Logs FINDING_ACTION_UPDATED and REVISION_COMMITTED to audit ledger.
    """
    sub_id = uuid.uuid4()
    rev1_id = uuid.uuid4()
    finding_id = uuid.uuid4()

    orig_text = "Welcome to BrandShield for cloud security."
    # Finding flags "BrandShield" at [11:22] with suggestion "BrandShield™"
    mock_finding = Finding(
        id=finding_id,
        revision_id=rev1_id,
        issue_category=FindingCategory.TERMINOLOGY,
        severity=SeverityLevel.HIGH,
        confidence_score=1.0,
        triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
        start_offset=11,
        end_offset=22,
        explanation_reason="Missing trademark symbol",
        suggested_correction="BrandShield™",
        detector_source=DetectorSource.DETERMINISTIC_RULE,
        is_automation_bias_audit=False,
        creator_action=CreatorAction.PENDING,
    )

    mock_rev1 = DocumentRevision(
        id=rev1_id,
        submission_id=sub_id,
        revision_number=1,
        parent_revision_id=None,
        content_text=orig_text,
        ast_span_map=[{"span_id": "s1", "start_char": 0, "end_char": len(orig_text)}],
        created_by_id=creator_user.id,
        sha256_content_hash="hash1",
        diff_summary=None,
    )

    mock_sub = Submission(
        id=sub_id,
        workspace_id=creator_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=creator_user.id,
        workflow_state=WorkflowState.TRIAGED,
        current_revision_id=rev1_id,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == Submission:
            return mock_sub
        if model == DocumentRevision:
            return mock_rev1
        if model == Finding:
            return mock_finding
        return None

    mock_session.get.side_effect = mock_get

    req = FindingResolutionRequest(
        action=CreatorAction.ACCEPT,
        comment="Accepted brand trademark insertion.",
    )

    res = await RevisionEngine.resolve_finding(
        session=mock_session,
        submission_id=sub_id,
        finding_id=finding_id,
        actor=creator_user,
        payload=req,
    )

    assert res.action == CreatorAction.ACCEPT
    assert res.applied_correction == "BrandShield™"
    assert res.new_revision_number == 2
    assert res.new_revision_id is not None
    assert res.workflow_state == WorkflowState.IN_CREATOR_REVISION

    # Verify original text was NOT modified
    assert mock_rev1.content_text == orig_text

    # Verify new revision was added with correct content
    added_objects = [call[0][0] for call in mock_session.add.call_args_list]
    new_rev = next(obj for obj in added_objects if isinstance(obj, DocumentRevision))
    assert new_rev.revision_number == 2
    assert new_rev.parent_revision_id == rev1_id
    assert new_rev.content_text == "Welcome to BrandShield™ for cloud security."
    assert new_rev.diff_summary is not None
    assert new_rev.diff_summary["lines_added"] >= 1

    # Verify finding was updated
    assert mock_finding.creator_action == CreatorAction.ACCEPT
    assert mock_finding.creator_comment == "Accepted brand trademark insertion."

    # Verify audit events were recorded
    audit_events = [obj for obj in added_objects if hasattr(obj, "action")]
    actions = {e.action for e in audit_events}
    assert AuditAction.FINDING_ACTION_UPDATED in actions
    assert AuditAction.REVISION_COMMITTED in actions


@pytest.mark.asyncio
async def test_resolve_finding_reject_no_text_mutation(creator_user):
    """
    Validates REJECT resolution:
    - Finding status updated to REJECTED with comment.
    - Content is not mutated; no new revision created.
    - Audit ledger event logged.
    """
    sub_id = uuid.uuid4()
    rev1_id = uuid.uuid4()
    finding_id = uuid.uuid4()

    mock_finding = Finding(
        id=finding_id,
        revision_id=rev1_id,
        issue_category=FindingCategory.TONE,
        severity=SeverityLevel.LOW,
        confidence_score=0.9,
        triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
        start_offset=0,
        end_offset=10,
        explanation_reason="Passive voice detected",
        suggested_correction="Active rewrite",
        detector_source=DetectorSource.DETERMINISTIC_RULE,
        creator_action=CreatorAction.PENDING,
    )

    mock_rev1 = DocumentRevision(
        id=rev1_id,
        submission_id=sub_id,
        revision_number=1,
        content_text="Original text",
        created_by_id=creator_user.id,
        sha256_content_hash="h1",
    )

    mock_sub = Submission(
        id=sub_id,
        workspace_id=creator_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=creator_user.id,
        workflow_state=WorkflowState.TRIAGED,
        current_revision_id=rev1_id,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == Submission:
            return mock_sub
        if model == DocumentRevision:
            return mock_rev1
        if model == Finding:
            return mock_finding
        return None

    mock_session.get.side_effect = mock_get

    req = FindingResolutionRequest(
        action=CreatorAction.REJECT,
        comment="Intentional stylistic choice for technical documentation.",
    )

    res = await RevisionEngine.resolve_finding(
        session=mock_session,
        submission_id=sub_id,
        finding_id=finding_id,
        actor=creator_user,
        payload=req,
    )

    assert res.action == CreatorAction.REJECT
    assert res.new_revision_id is None
    assert mock_finding.creator_action == CreatorAction.REJECT
    assert mock_finding.creator_comment == "Intentional stylistic choice for technical documentation."
    assert mock_sub.workflow_state == WorkflowState.IN_CREATOR_REVISION


@pytest.mark.asyncio
async def test_resolve_finding_edit_custom_replacement(creator_user):
    """Validates EDIT resolution: custom text replaces the finding span and creates v2."""
    sub_id = uuid.uuid4()
    rev1_id = uuid.uuid4()
    finding_id = uuid.uuid4()

    mock_finding = Finding(
        id=finding_id,
        revision_id=rev1_id,
        issue_category=FindingCategory.TERMINOLOGY,
        severity=SeverityLevel.HIGH,
        confidence_score=1.0,
        triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
        start_offset=19,
        end_offset=23,
        explanation_reason="Forbidden term 'cure'",
        suggested_correction="resolve",
        detector_source=DetectorSource.DETERMINISTIC_RULE,
        creator_action=CreatorAction.PENDING,
    )

    mock_rev1 = DocumentRevision(
        id=rev1_id,
        submission_id=sub_id,
        revision_number=1,
        content_text="This platform is a cure for latency.",
        created_by_id=creator_user.id,
        sha256_content_hash="h1",
    )

    mock_sub = Submission(
        id=sub_id,
        workspace_id=creator_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=creator_user.id,
        workflow_state=WorkflowState.TRIAGED,
        current_revision_id=rev1_id,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == Submission:
            return mock_sub
        if model == DocumentRevision:
            return mock_rev1
        if model == Finding:
            return mock_finding
        return None

    mock_session.get.side_effect = mock_get

    req = FindingResolutionRequest(
        action=CreatorAction.EDIT,
        edited_text="verified mitigation",
        comment="Custom tailored phrasing.",
    )

    res = await RevisionEngine.resolve_finding(
        session=mock_session,
        submission_id=sub_id,
        finding_id=finding_id,
        actor=creator_user,
        payload=req,
    )

    assert res.action == CreatorAction.EDIT
    assert res.applied_correction == "verified mitigation"
    assert res.new_revision_number == 2

    added_objects = [call[0][0] for call in mock_session.add.call_args_list]
    new_rev = next(obj for obj in added_objects if isinstance(obj, DocumentRevision))
    assert new_rev.content_text == "This platform is a verified mitigation for latency."


# ==============================================================================
# 3. Human Reviewer Sign-Off Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_reviewer_approval_success_with_verified_audits(reviewer_user):
    """
    Validates reviewer sign-off:
    - All automation-bias audit findings are explicitly confirmed.
    - Submission transitions to APPROVED.
    - ReviewDecision persisted and REVIEW_DECIDED audit logged.
    """
    sub_id = uuid.uuid4()
    rev_id = uuid.uuid4()
    audit_finding_id = uuid.uuid4()

    mock_sub = Submission(
        id=sub_id,
        workspace_id=reviewer_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.IN_HUMAN_REVIEW,
        current_revision_id=rev_id,
    )

    # Finding flagged by automation-bias safeguard
    audit_finding = Finding(
        id=audit_finding_id,
        revision_id=rev_id,
        issue_category=FindingCategory.TERMINOLOGY,
        severity=SeverityLevel.HIGH,
        confidence_score=1.0,
        triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
        start_offset=0,
        end_offset=10,
        explanation_reason="Automated detection",
        is_automation_bias_audit=True,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == Submission:
            return mock_sub
        return None

    mock_session.get.side_effect = mock_get

    # Mock finding query
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [audit_finding]
    mock_session.execute.return_value = mock_res

    req = ReviewSubmissionRequest(
        decision=ReviewSignOff.APPROVED,
        comments="All primary legal citations and trademarks substantiated.",
        stipulations={"market_scope": "North America B2B"},
        finding_verifications=[
            FindingVerificationInput(finding_id=audit_finding_id, verified=True, comment="Primary source verified")
        ],
        inline_comments=[
            InlineCommentInput(start_offset=0, end_offset=10, comment="Verified against legal trademark register")
        ],
    )

    decision = await WorkflowReviewService.execute_review_decision(
        session=mock_session,
        submission_id=sub_id,
        reviewer=reviewer_user,
        payload=req,
    )

    assert decision.decision == ReviewSignOff.APPROVED
    assert decision.reviewer_id == reviewer_user.id
    assert mock_sub.workflow_state == WorkflowState.APPROVED
    assert mock_sub.assigned_reviewer_id == reviewer_user.id

    # Verify audit ledger recorded REVIEW_DECIDED
    added_objects = [call[0][0] for call in mock_session.add.call_args_list]
    audit_event = next(obj for obj in added_objects if hasattr(obj, "action") and obj.action == AuditAction.REVIEW_DECIDED)
    assert audit_event.payload["decision"] == "APPROVED"


@pytest.mark.asyncio
async def test_reviewer_approval_fails_without_verifying_automation_bias_audit(reviewer_user):
    """
    ANTI-RUBBER-STAMPING TEST:
    Approval must be REJECTED if an automation-bias audit finding is not explicitly confirmed.
    """
    sub_id = uuid.uuid4()
    rev_id = uuid.uuid4()
    unverified_audit_id = uuid.uuid4()

    mock_sub = Submission(
        id=sub_id,
        workspace_id=reviewer_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.IN_HUMAN_REVIEW,
        current_revision_id=rev_id,
    )

    audit_finding = Finding(
        id=unverified_audit_id,
        revision_id=rev_id,
        issue_category=FindingCategory.TERMINOLOGY,
        severity=SeverityLevel.HIGH,
        confidence_score=1.0,
        triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
        start_offset=0,
        end_offset=10,
        explanation_reason="Automated detection",
        is_automation_bias_audit=True,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == Submission:
            return mock_sub
        return None

    mock_session.get.side_effect = mock_get

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [audit_finding]
    mock_session.execute.return_value = mock_res

    # Reviewer attempts approval WITHOUT verifying unverified_audit_id
    req = ReviewSubmissionRequest(
        decision=ReviewSignOff.APPROVED,
        comments="Rubber-stamping without verifying audit safeguards.",
        finding_verifications=[],  # Empty!
    )

    with pytest.raises(ValidationErrorProblem) as exc_info:
        await WorkflowReviewService.execute_review_decision(
            session=mock_session,
            submission_id=sub_id,
            reviewer=reviewer_user,
            payload=req,
        )

    assert exc_info.value.status_code == 422
    assert "Automation-Bias Safeguard Protection" in exc_info.value.detail
    assert str(unverified_audit_id) in exc_info.value.detail


@pytest.mark.asyncio
async def test_reviewer_request_changes(reviewer_user):
    """Validates reviewer requesting changes transitions workflow to CHANGES_REQUESTED."""
    sub_id = uuid.uuid4()
    rev_id = uuid.uuid4()

    mock_sub = Submission(
        id=sub_id,
        workspace_id=reviewer_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.IN_HUMAN_REVIEW,
        current_revision_id=rev_id,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == Submission:
            return mock_sub
        return None

    mock_session.get.side_effect = mock_get

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res

    req = ReviewSubmissionRequest(
        decision=ReviewSignOff.CHANGES_REQUESTED,
        comments="Please rephrase paragraph 2 in active voice.",
    )

    decision = await WorkflowReviewService.execute_review_decision(
        session=mock_session,
        submission_id=sub_id,
        reviewer=reviewer_user,
        payload=req,
    )

    assert decision.decision == ReviewSignOff.CHANGES_REQUESTED
    assert mock_sub.workflow_state == WorkflowState.CHANGES_REQUESTED


# ==============================================================================
# 4. Revision Lineage & Side-by-Side Token Diff Tests
# ==============================================================================

def test_diff_service_token_level_comparison():
    """Validates side-by-side token diff chunk computation with exact character spans."""
    old_text = "Our platform is secure and fast."
    new_text = "Our platform is extremely secure and remarkably fast."

    chunks = DiffService.compute_token_diff(old_text, new_text)
    assert len(chunks) >= 3

    # Check for 'insert' opcodes
    insert_chunks = [c for c in chunks if c.op in ("insert", "replace")]
    assert len(insert_chunks) >= 1

    # Check unified line diff
    line_diff = DiffService.compute_line_diff(old_text, new_text)
    assert line_diff["lines_added"] >= 1
    assert line_diff["lines_removed"] >= 1


@pytest.mark.asyncio
async def test_get_revision_lineage_and_diff_endpoint(workspace_id):
    """
    Validates DiffService.get_revision_diff:
    Returns complete lineage DAG from v1 to latest and computes exact token diffs.
    """
    sub_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    mock_sub = Submission(
        id=sub_id,
        workspace_id=workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.IN_CREATOR_REVISION,
    )

    rev1 = DocumentRevision(
        id=uuid.uuid4(),
        submission_id=sub_id,
        revision_number=1,
        parent_revision_id=None,
        content_text="BrandShield is great.",
        ast_span_map=[],
        created_by_id=uuid.uuid4(),
        sha256_content_hash="h1",
        created_at=now,
    )

    rev2 = DocumentRevision(
        id=uuid.uuid4(),
        submission_id=sub_id,
        revision_number=2,
        parent_revision_id=rev1.id,
        content_text="BrandShield™ is exceptional.",
        ast_span_map=[],
        created_by_id=uuid.uuid4(),
        sha256_content_hash="h2",
        created_at=now,
    )

    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == Submission:
            return mock_sub
        return None

    mock_session.get.side_effect = mock_get

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [rev1, rev2]
    mock_session.execute.return_value = mock_res

    res = await DiffService.get_revision_diff(
        session=mock_session,
        submission_id=sub_id,
        from_revision=1,
        to_revision=2,
    )

    assert res.submission_id == sub_id
    assert res.from_revision == 1
    assert res.to_revision == 2
    assert len(res.lineage) == 2
    assert res.lineage[0].revision_number == 1
    assert res.lineage[1].revision_number == 2
    assert res.lineage[1].parent_revision_id == rev1.id
    assert len(res.token_diff) >= 1
    assert res.lines_added >= 1


# ==============================================================================
# 5. HTTP API Integration Tests (FastAPI Endpoints)
# ==============================================================================

@pytest.mark.asyncio
async def test_api_workflow_resolve_finding_accept(creator_user, creator_token):
    """Validates HTTP POST /api/v1/submissions/{id}/findings/{finding_id}/resolve with ACCEPT."""
    sub_id = uuid.uuid4()
    rev1_id = uuid.uuid4()
    finding_id = uuid.uuid4()

    mock_finding = Finding(
        id=finding_id,
        revision_id=rev1_id,
        issue_category=FindingCategory.TERMINOLOGY,
        severity=SeverityLevel.HIGH,
        confidence_score=1.0,
        triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
        start_offset=11,
        end_offset=22,
        explanation_reason="Missing trademark symbol",
        suggested_correction="BrandShield™",
        detector_source=DetectorSource.DETERMINISTIC_RULE,
        is_automation_bias_audit=False,
        creator_action=CreatorAction.PENDING,
    )

    mock_rev1 = DocumentRevision(
        id=rev1_id,
        submission_id=sub_id,
        revision_number=1,
        parent_revision_id=None,
        content_text="Welcome to BrandShield for security.",
        ast_span_map=[],
        created_by_id=creator_user.id,
        sha256_content_hash="hash1",
    )

    mock_sub = Submission(
        id=sub_id,
        workspace_id=creator_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=creator_user.id,
        workflow_state=WorkflowState.TRIAGED,
        current_revision_id=rev1_id,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        if model == Submission:
            return mock_sub
        if model == DocumentRevision:
            return mock_rev1
        if model == Finding:
            return mock_finding
        return None

    mock_session.get.side_effect = mock_get

    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                f"/api/v1/submissions/{sub_id}/findings/{finding_id}/resolve",
                headers={"Authorization": f"Bearer {creator_token}"},
                json={"action": "ACCEPT", "comment": "Accepted trademark correction."},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["action"] == "ACCEPTED"
            assert data["applied_correction"] == "BrandShield™"
            assert data["new_revision_number"] == 2
            assert data["workflow_state"] == "IN_CREATOR_REVISION"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_workflow_resolve_finding_reject(creator_user, creator_token):
    """Validates HTTP POST /api/v1/submissions/{id}/findings/{finding_id}/resolve with REJECT."""
    sub_id = uuid.uuid4()
    rev1_id = uuid.uuid4()
    finding_id = uuid.uuid4()

    mock_finding = Finding(
        id=finding_id,
        revision_id=rev1_id,
        issue_category=FindingCategory.TONE,
        severity=SeverityLevel.LOW,
        confidence_score=0.9,
        triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
        start_offset=0,
        end_offset=5,
        explanation_reason="Tone suggestion",
        suggested_correction="Rewrite",
        detector_source=DetectorSource.DETERMINISTIC_RULE,
        creator_action=CreatorAction.PENDING,
    )

    mock_rev1 = DocumentRevision(
        id=rev1_id,
        submission_id=sub_id,
        revision_number=1,
        content_text="Hello world.",
        created_by_id=creator_user.id,
        sha256_content_hash="h1",
    )

    mock_sub = Submission(
        id=sub_id,
        workspace_id=creator_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=creator_user.id,
        workflow_state=WorkflowState.TRIAGED,
        current_revision_id=rev1_id,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        if model == Submission:
            return mock_sub
        if model == DocumentRevision:
            return mock_rev1
        if model == Finding:
            return mock_finding
        return None

    mock_session.get.side_effect = mock_get

    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                f"/api/v1/submissions/{sub_id}/findings/{finding_id}/resolve",
                headers={"Authorization": f"Bearer {creator_token}"},
                json={"action": "REJECT", "comment": "Intentional wording."},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["action"] == "REJECTED"
            assert data["new_revision_id"] is None
            assert data["workflow_state"] == "IN_CREATOR_REVISION"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_workflow_submit_for_review(creator_user, creator_token):
    """Validates HTTP POST /api/v1/submissions/{id}/submit-for-review."""
    sub_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    mock_sub = Submission(
        id=sub_id,
        workspace_id=creator_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=creator_user.id,
        workflow_state=WorkflowState.IN_CREATOR_REVISION,
        title="Enterprise Marketing Pitch",
        document_type="TEXT",
        created_at=now,
        updated_at=now,
    )

    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        if model == Submission:
            return mock_sub
        return None

    mock_session.get.side_effect = mock_get

    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                f"/api/v1/submissions/{sub_id}/submit-for-review",
                headers={"Authorization": f"Bearer {creator_token}"},
            )

            assert resp.status_code == 200
            assert resp.json()["workflow_state"] == "IN_HUMAN_REVIEW"
            assert mock_sub.workflow_state == WorkflowState.IN_HUMAN_REVIEW
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_workflow_human_review_approval_with_audits(reviewer_user, reviewer_token):
    """Validates HTTP POST /api/v1/submissions/{id}/review with APPROVED decision and audit verification."""
    sub_id = uuid.uuid4()
    rev1_id = uuid.uuid4()
    bias_finding_id = uuid.uuid4()

    mock_sub = Submission(
        id=sub_id,
        workspace_id=reviewer_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.IN_HUMAN_REVIEW,
        current_revision_id=rev1_id,
    )

    bias_finding = Finding(
        id=bias_finding_id,
        revision_id=rev1_id,
        issue_category=FindingCategory.UNSUBSTANTIATED_CLAIM,
        severity=SeverityLevel.HIGH,
        confidence_score=0.9,
        triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
        start_offset=0,
        end_offset=10,
        explanation_reason="Stochastic audit check",
        is_automation_bias_audit=True,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return reviewer_user
        if model == Submission:
            return mock_sub
        return None

    mock_session.get.side_effect = mock_get

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [bias_finding]
    mock_exec_res = MagicMock()
    mock_exec_res.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_exec_res

    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                f"/api/v1/submissions/{sub_id}/review",
                headers={"Authorization": f"Bearer {reviewer_token}"},
                json={
                    "decision": "APPROVED",
                    "comments": "Compliance verification completed and approved.",
                    "finding_verifications": [
                        {"finding_id": str(bias_finding_id), "verified": True, "comment": "Checked manual fact"}
                    ],
                },
            )

            assert resp.status_code == 201
            assert resp.json()["decision"] == "APPROVED"
            assert mock_sub.workflow_state == WorkflowState.APPROVED
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_workflow_human_review_approval_blocked_without_audit_verification(
    reviewer_user, reviewer_token
):
    """Validates approval rejection if automation-bias audit findings are not verified."""
    sub_id = uuid.uuid4()
    rev1_id = uuid.uuid4()
    bias_finding_id = uuid.uuid4()

    mock_sub = Submission(
        id=sub_id,
        workspace_id=reviewer_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.IN_HUMAN_REVIEW,
        current_revision_id=rev1_id,
    )

    bias_finding = Finding(
        id=bias_finding_id,
        revision_id=rev1_id,
        issue_category=FindingCategory.UNSUBSTANTIATED_CLAIM,
        severity=SeverityLevel.HIGH,
        confidence_score=0.9,
        triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
        start_offset=0,
        end_offset=10,
        explanation_reason="Stochastic audit check",
        is_automation_bias_audit=True,
    )

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return reviewer_user
        if model == Submission:
            return mock_sub
        return None

    mock_session.get.side_effect = mock_get

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [bias_finding]
    mock_exec_res = MagicMock()
    mock_exec_res.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_exec_res

    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                f"/api/v1/submissions/{sub_id}/review",
                headers={"Authorization": f"Bearer {reviewer_token}"},
                json={
                    "decision": "APPROVED",
                    "comments": "Attempting approval without verifying audit findings.",
                    "finding_verifications": [],
                },
            )

            assert resp.status_code == 422
            problem = resp.json()
            assert problem["title"] == "Validation Error"
            assert "automation-bias safeguard" in problem["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_workflow_human_review_creator_role_forbidden(creator_user, creator_token):
    """Guarantees Creators are strictly forbidden from executing reviewer sign-off."""
    sub_id = uuid.uuid4()
    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        return None

    mock_session.get.side_effect = mock_get
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                f"/api/v1/submissions/{sub_id}/review",
                headers={"Authorization": f"Bearer {creator_token}"},
                json={
                    "decision": "APPROVED",
                    "comments": "Creator attempting self-approval.",
                },
            )

            assert resp.status_code == 403
            problem = resp.json()
            assert problem["title"] == "Forbidden Access"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_workflow_revision_diff(creator_user, creator_token):
    """Validates HTTP GET /api/v1/submissions/{id}/revisions/diff."""
    sub_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    mock_sub = Submission(
        id=sub_id,
        workspace_id=creator_user.workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=creator_user.id,
        workflow_state=WorkflowState.IN_CREATOR_REVISION,
    )

    rev1 = DocumentRevision(
        id=uuid.uuid4(),
        submission_id=sub_id,
        revision_number=1,
        parent_revision_id=None,
        content_text="BrandShield protects enterprise assets.",
        ast_span_map=[],
        created_by_id=creator_user.id,
        sha256_content_hash="h1",
        created_at=now,
    )

    rev2 = DocumentRevision(
        id=uuid.uuid4(),
        submission_id=sub_id,
        revision_number=2,
        parent_revision_id=rev1.id,
        content_text="BrandShield™ protects critical enterprise assets.",
        ast_span_map=[],
        created_by_id=creator_user.id,
        sha256_content_hash="h2",
        created_at=now,
    )

    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        if model == Submission:
            return mock_sub
        return None

    mock_session.get.side_effect = mock_get

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [rev1, rev2]
    mock_session.execute.return_value = mock_res

    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get(
                f"/api/v1/submissions/{sub_id}/revisions/diff?from_revision=1&to_revision=2",
                headers={"Authorization": f"Bearer {creator_token}"},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["submission_id"] == str(sub_id)
            assert data["from_revision"] == 1
            assert data["to_revision"] == 2
            assert len(data["lineage"]) == 2
            assert len(data["token_diff"]) >= 1
            assert "unified_diff" in data
            assert data["lines_added"] >= 1
    finally:
        app.dependency_overrides.clear()
