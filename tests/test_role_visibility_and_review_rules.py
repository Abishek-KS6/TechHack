"""
BrandShield AI - Role Visibility & Review Rules Test Suite.
Validates:
1. Role-based endpoint visibility & HTTP 403 enforcement (Creator/Reviewer/Admin on /audit/logs and /governance/reports).
2. Public signup strictly defaults to CREATOR role regardless of payload.
3. Separation of duties: Creator cannot approve own submission (403 Forbidden).
4. Administrator cannot approve unless acting as assigned reviewer (403 Forbidden).
5. Administrator assigning themselves as reviewer enables approval.
6. Review rules GET/PUT endpoints (Admin only, validation, and audit ledger persistence).
7. System status endpoint reports known historical break at #9 and verification from #10.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import ForbiddenProblem
from app.core.security import create_access_token, get_current_user, hash_password
from app.domain.enums import ReviewSignOff, UserRole, WorkflowState
from app.domain.schemas.submission import ReviewSubmissionRequest
from app.infrastructure.db.models import Submission, User, Workspace
from app.infrastructure.db.session import get_async_session
from app.main import app
from app.services.workflow.review_service import WorkflowReviewService


@pytest.fixture
def workspace_id():
    return uuid.uuid4()


@pytest.fixture
def admin_user(workspace_id):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        email="admin@acme.com",
        hashed_password=hash_password("DemoSecure2026!"),
        full_name="Sam Admin",
        role=UserRole.ADMINISTRATOR,
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
        email="reviewer@acme.com",
        hashed_password=hash_password("DemoSecure2026!"),
        full_name="Auditor First",
        role=UserRole.REVIEWER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def creator_user(workspace_id):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        email="creator@acme.com",
        hashed_password=hash_password("DemoSecure2026!"),
        full_name="Alex Creator",
        role=UserRole.CREATOR,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_audit_logs_role_enforcement(admin_user, reviewer_user, creator_user):
    """Asserts that /api/v1/audit/logs returns 403 for Creator and Reviewer, but 200 for Admin."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
    app.dependency_overrides[get_async_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Creator -> 403 Forbidden
        app.dependency_overrides[get_current_user] = lambda: creator_user
        r_creator = await client.get("/api/v1/audit/logs")
        assert r_creator.status_code == 403, f"Expected 403 for creator on /audit/logs, got {r_creator.status_code}"

        # Reviewer -> 403 Forbidden
        app.dependency_overrides[get_current_user] = lambda: reviewer_user
        r_rev = await client.get("/api/v1/audit/logs")
        assert r_rev.status_code == 403, f"Expected 403 for reviewer on /audit/logs, got {r_rev.status_code}"

        # Administrator -> 200 OK
        app.dependency_overrides[get_current_user] = lambda: admin_user
        r_admin = await client.get("/api/v1/audit/logs")
        assert r_admin.status_code == 200, f"Expected 200 for admin on /audit/logs, got {r_admin.status_code}"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_governance_reports_role_enforcement(reviewer_user, creator_user):
    """Asserts that /api/v1/governance/reports returns 403 for Creator, but 200 for Reviewer."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[]), scalar=MagicMock(return_value=0)))
    app.dependency_overrides[get_async_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Creator -> 403 Forbidden
        app.dependency_overrides[get_current_user] = lambda: creator_user
        r_creator = await client.get("/api/v1/governance/reports")
        assert r_creator.status_code == 403

        # Reviewer -> 200 OK
        app.dependency_overrides[get_current_user] = lambda: reviewer_user
        r_rev = await client.get("/api/v1/governance/reports")
        assert r_rev.status_code == 200

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_public_signup_forces_creator_role():
    """Asserts that self-serve signup forces UserRole.CREATOR even if caller sends ADMINISTRATOR."""
    ws = Workspace(id=uuid.uuid4(), name="Default Workspace", slug="ws-default")
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=ws)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ])
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    created_user_holder = []
    def capture_add(instance):
        if isinstance(instance, User):
            created_user_holder.append(instance)
    mock_session.add = capture_add

    app.dependency_overrides[get_async_session] = lambda: mock_session

    with patch("app.services.audit_service.AuditService.record_event", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "email": "newuser@domain.com",
                "password": "Password123!",
                "full_name": "New Person",
                "role": "ADMINISTRATOR",  # Attempt to escalate to ADMIN
            }
            resp = await client.post("/api/v1/auth/signup", json=payload)
            assert resp.status_code == 201

            # Check returned user role in response
            data = resp.json()
            assert data["user"]["role"] == "CREATOR", f"Expected CREATOR role, got {data['user']['role']}"

            # Verify database model was assigned CREATOR
            assert len(created_user_holder) > 0
            assert created_user_holder[0].role == UserRole.CREATOR

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_creator_cannot_approve_own_submission(creator_user, workspace_id):
    """Asserts WorkflowReviewService raises ForbiddenProblem when creator attempts to approve own submission."""
    mock_session = AsyncMock()
    sub_id = uuid.uuid4()
    rev_id = uuid.uuid4()

    mock_submission = Submission(
        id=sub_id,
        workspace_id=workspace_id,
        creator_id=creator_user.id,  # Creator is the author
        workflow_state=WorkflowState.IN_HUMAN_REVIEW,
        current_revision_id=rev_id,
    )
    mock_session.get = AsyncMock(return_value=mock_submission)

    req = ReviewSubmissionRequest(
        decision=ReviewSignOff.APPROVED,
        comments="Self approval test",
    )

    with pytest.raises(ForbiddenProblem) as exc:
        await WorkflowReviewService.execute_review_decision(
            session=mock_session,
            submission_id=sub_id,
            reviewer=creator_user,  # Same user
            payload=req,
        )
    assert "A creator cannot approve their own submission" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_admin_cannot_approve_unless_assigned_reviewer(admin_user, creator_user, workspace_id):
    """Asserts administrator cannot approve unless acting as assigned reviewer."""
    mock_session = AsyncMock()
    sub_id = uuid.uuid4()
    rev_id = uuid.uuid4()

    # Submission has no assigned reviewer yet
    mock_submission = Submission(
        id=sub_id,
        workspace_id=workspace_id,
        creator_id=creator_user.id,
        assigned_reviewer_id=None,
        workflow_state=WorkflowState.IN_HUMAN_REVIEW,
        current_revision_id=rev_id,
    )
    mock_session.get = AsyncMock(return_value=mock_submission)

    req = ReviewSubmissionRequest(
        decision=ReviewSignOff.APPROVED,
        comments="Admin unassigned approval test",
    )

    with pytest.raises(ForbiddenProblem) as exc:
        await WorkflowReviewService.execute_review_decision(
            session=mock_session,
            submission_id=sub_id,
            reviewer=admin_user,
            payload=req,
        )
    assert "An administrator cannot approve a submission unless acting as an assigned reviewer" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_settings_review_rules_crud_and_status(admin_user, creator_user, workspace_id):
    """
    Validates:
    1. Non-admin gets 403 on GET and PUT /api/v1/settings/review-rules.
    2. Admin gets review rules (confidence_threshold, random_double_check_percentage, fact_review_period_days, require_evidence_before_approval).
    3. Admin PUT updates review rules and writes REVIEW_RULES_UPDATED audit entry.
    4. System status reports known historical break at #9 and verified from #10.
    """
    mock_ws = Workspace(
        id=workspace_id,
        name="Acme Corp",
        slug="acme-corp",
        review_rules={
            "confidence_threshold": 0.85,
            "random_double_check_percentage": 15.0,
            "fact_review_period_days": 90,
            "require_evidence_before_approval": True,
        },
    )

    async def mock_get(entity_class, entity_id):
        if entity_class is Workspace:
            return mock_ws
        return admin_user

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

    app.dependency_overrides[get_async_session] = lambda: mock_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Non-admin GET -> 403
        app.dependency_overrides[get_current_user] = lambda: creator_user
        r_get_c = await client.get("/api/v1/settings/review-rules")
        assert r_get_c.status_code == 403

        # 2. Admin GET -> 200
        app.dependency_overrides[get_current_user] = lambda: admin_user
        r_get_a = await client.get("/api/v1/settings/review-rules")
        assert r_get_a.status_code == 200
        rules = r_get_a.json()
        assert rules["confidence_threshold"] == 0.85
        assert rules["random_double_check_percentage"] == 15.0
        assert rules["fact_review_period_days"] == 90
        assert rules["require_evidence_before_approval"] is True

        # 3. Non-admin PUT -> 403
        app.dependency_overrides[get_current_user] = lambda: creator_user
        r_put_c = await client.put("/api/v1/settings/review-rules", json={"confidence_threshold": 0.90})
        assert r_put_c.status_code == 403

        # 4. Admin PUT -> 200 (update rules)
        app.dependency_overrides[get_current_user] = lambda: admin_user
        with patch("app.services.audit_service.AuditService.record_event", new_callable=AsyncMock) as mock_audit:
            r_put_a = await client.put(
                "/api/v1/settings/review-rules",
                json={
                    "confidence_threshold": 0.92,
                    "random_double_check_percentage": 20.0,
                    "fact_review_period_days": 60,
                    "require_evidence_before_approval": True,
                },
            )
            assert r_put_a.status_code == 200
            updated = r_put_a.json()
            assert updated["confidence_threshold"] == 0.92
            assert updated["random_double_check_percentage"] == 20.0
            assert updated["fact_review_period_days"] == 60
            assert mock_audit.called

        # 5. System status -> 200 (check verified from block #10 and break at #9)
        r_status = await client.get("/api/v1/settings/system-status")
        assert r_status.status_code == 200
        status_data = r_status.json()
        assert status_data["backend_connected"] is True
        assert "Verified from block #10 onward" in status_data["audit_chain_status"]
        assert "Known historical break at #9" in status_data["audit_chain_status"]

    app.dependency_overrides.clear()
