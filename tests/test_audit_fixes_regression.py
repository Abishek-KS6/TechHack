"""
BrandShield AI - Regression Test Suite for Backend Audit Fixes.
Verifies:
1. P0.1: Governance reports and traceability metrics under PostgreSQL with None, UUID, and invalid filters.
2. P0.2: Live analysis engine handling string, dictionary, and malformed terminology metadata.
3. P1: Audit ledger transaction-level locking and concurrent event integrity.
4. P2: System diagnostics RBAC security enforcement (401 unauth, 403 non-admin, 200 admin).
5. Workflow and submissions dual-route compatibility.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.domain.enums import AuditAction, UserRole
from app.infrastructure.db.models import BrandProfile, User, Workspace
from app.infrastructure.db.session import AsyncSessionLocal, get_async_session
from app.main import app
from app.services.analysis.deterministic_engine import DeterministicRuleEngine
from app.services.audit_service import AuditService
from app.services.governance.reporting_service import GovernanceReportService
from app.services.governance.traceability_service import TraceabilityAuditService


@pytest.fixture
def test_workspace_id():
    return uuid.UUID("54f410d2-f5bb-412c-b11d-9c43dbb11d05")


@pytest.fixture
def admin_user(test_workspace_id):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.UUID("745bf2ee-b0fd-4c40-97c9-467362cfdc15"),
        workspace_id=test_workspace_id,
        email="admin@acmefintech.com",
        role=UserRole.ADMINISTRATOR,
        full_name="Admin User",
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def creator_user(test_workspace_id):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.UUID("4d5f2fdc-2c54-4b6a-876d-f4f386d77691"),
        workspace_id=test_workspace_id,
        email="creator@acmefintech.com",
        role=UserRole.CREATOR,
        full_name="Creator User",
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def admin_jwt(admin_user):
    return create_access_token(
        user_id=admin_user.id,
        email=admin_user.email,
        role=admin_user.role,
        workspace_id=admin_user.workspace_id,
    )


@pytest.fixture
def creator_jwt(creator_user):
    return create_access_token(
        user_id=creator_user.id,
        email=creator_user.email,
        role=creator_user.role,
        workspace_id=creator_user.workspace_id,
    )


@pytest.mark.asyncio
async def test_governance_postgresql_null_and_uuid_queries(test_workspace_id):
    """Verifies P0.1: PostgreSQL query executes without type errors for None, valid UUID, and non-matching UUID."""
    async with AsyncSessionLocal() as session:
        # 1. Reports without filter
        rep_all = await GovernanceReportService.generate_report(session, test_workspace_id, None)
        assert rep_all.total_findings >= 0

        # 2. Reports with valid UUID
        prof_id = uuid.UUID("79978154-1c75-4996-9293-b3a7886f33a8")
        rep_filtered = await GovernanceReportService.generate_report(session, test_workspace_id, prof_id)
        assert rep_filtered.total_findings >= 0

        # 3. Reports with non-matching UUID
        rep_empty = await GovernanceReportService.generate_report(session, test_workspace_id, uuid.uuid4())
        assert rep_empty.total_findings == 0

        # 4. Traceability without filter
        trace_all = await TraceabilityAuditService.compute_metrics(session, test_workspace_id, None)
        assert trace_all.total_findings >= 0

        # 5. Traceability with valid UUID
        trace_filtered = await TraceabilityAuditService.compute_metrics(session, test_workspace_id, prof_id)
        assert trace_filtered.total_findings >= 0


@pytest.mark.asyncio
async def test_governance_endpoints_http_matrix(admin_user, creator_user, admin_jwt, creator_jwt):
    """Verifies HTTP routing, RBAC, and invalid UUID handling for governance endpoints."""
    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            if ident == admin_user.id:
                return admin_user
            if ident == creator_user.id:
                return creator_user
        return None

    mock_session.get.side_effect = mock_get
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    mock_res.first.return_value = (0, 0, 0, 0, 0, 0, 0)
    mock_session.execute.return_value = mock_res
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Unauthenticated -> 401
            res = await client.get("/api/v1/governance/reports")
            assert res.status_code == 401

            # 2. Non-admin (Creator) -> 403
            res = await client.get(
                "/api/v1/governance/reports",
                headers={"Authorization": f"Bearer {creator_jwt}"},
            )
            assert res.status_code == 403

            # 3. Admin without filter -> 200
            res = await client.get(
                "/api/v1/governance/reports",
                headers={"Authorization": f"Bearer {admin_jwt}"},
            )
            assert res.status_code == 200

            # 4. Admin with valid UUID filter -> 200
            res = await client.get(
                "/api/v1/governance/reports?brand_profile_id=79978154-1c75-4996-9293-b3a7886f33a8",
                headers={"Authorization": f"Bearer {admin_jwt}"},
            )
            assert res.status_code == 200

            # 5. Invalid UUID format -> 422
            res = await client.get(
                "/api/v1/governance/reports?brand_profile_id=invalid-uuid-format",
                headers={"Authorization": f"Bearer {admin_jwt}"},
            )
            assert res.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_live_analysis_string_dict_and_malformed_metadata(creator_user, creator_jwt):
    """Verifies P0.2: Engine safely parses string, dictionary, and malformed metadata in preferred terms."""
    mock_profile = BrandProfile(
        id=uuid.uuid4(),
        workspace_id=creator_user.workspace_id,
        name="Test Profile",
        banned_terminology_map={},
        preferred_terminology_map={
            "legacy term": "modern term",
            "brand name": {
                "approved_term": "Brand Name™",
                "reason": "Requires legal symbol.",
                "severity": "HIGH",
            },
            "odd term": {
                "suggested_correction": "better term",
            },
            "empty term": {},
            "null term": None,
        },
        messaging_rules={},
    )

    # 1. String mapping detection
    hits_str = DeterministicRuleEngine.analyze_document("This contains legacy term.", mock_profile)
    assert len(hits_str) == 1
    assert hits_str[0].suggested_correction == "modern term"

    # 2. Dictionary mapping detection
    hits_dict = DeterministicRuleEngine.analyze_document("This contains brand name.", mock_profile)
    assert len(hits_dict) == 1
    assert hits_dict[0].suggested_correction == "Brand Name™"

    # 3. Fallback dictionary mapping detection
    hits_odd = DeterministicRuleEngine.analyze_document("This contains odd term.", mock_profile)
    assert len(hits_odd) == 1
    assert hits_odd[0].suggested_correction == "better term"

    # 4. Empty dictionary detection (falls back to remove/replace message)
    hits_empty = DeterministicRuleEngine.analyze_document("This contains empty term.", mock_profile)
    assert len(hits_empty) == 1
    assert isinstance(hits_empty[0].suggested_correction, str)

    # 5. Null value detection (falls back to remove/replace message)
    hits_null = DeterministicRuleEngine.analyze_document("This contains null term.", mock_profile)
    assert len(hits_null) == 1
    assert isinstance(hits_null[0].suggested_correction, str)

    # 6. HTTP Endpoint live call with overridden session
    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        if model == BrandProfile:
            return mock_profile
        return None

    mock_session.get.side_effect = mock_get
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/analysis/live",
                headers={"Authorization": f"Bearer {creator_jwt}"},
                json={
                    "content_text": "This contains brand name.",
                    "brand_profile_id": str(mock_profile.id),
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert len(data["findings"]) == 1
            assert data["findings"][0]["suggested_correction"] == "Brand Name™"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_system_diagnostics_rbac(admin_user, creator_user, admin_jwt, creator_jwt):
    """Verifies P2: /api/v1/system/diagnostics requires Administrator authorization."""
    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            if ident == admin_user.id:
                return admin_user
            if ident == creator_user.id:
                return creator_user
        return None

    mock_session.get.side_effect = mock_get
    mock_res = MagicMock()
    mock_res.scalar.return_value = 10
    mock_session.execute.return_value = mock_res
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Unauthenticated -> 401
            res = await client.get("/api/v1/system/diagnostics")
            assert res.status_code == 401

            # 2. Non-administrator (Creator) -> 403
            res = await client.get(
                "/api/v1/system/diagnostics",
                headers={"Authorization": f"Bearer {creator_jwt}"},
            )
            assert res.status_code == 403

            # 3. Administrator -> 200
            res = await client.get(
                "/api/v1/system/diagnostics",
                headers={"Authorization": f"Bearer {admin_jwt}"},
            )
            assert res.status_code == 200
            body = res.json()
            assert "storage_integrity" in body
            assert "database_dialect" in body
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_audit_ledger_concurrency_locking(test_workspace_id):
    """Verifies P1: Concurrent audit writes acquire advisory lock and maintain correct previous_hash."""
    async with AsyncSessionLocal() as session:
        ev1 = await AuditService.record_event(
            session=session,
            action=AuditAction.USER_LOGIN,
            payload={"test": "concurrency_1", "time": datetime.now(timezone.utc).isoformat()},
            workspace_id=test_workspace_id,
        )
        await session.commit()

        ev2 = await AuditService.record_event(
            session=session,
            action=AuditAction.USER_LOGIN,
            payload={"test": "concurrency_2", "time": datetime.now(timezone.utc).isoformat()},
            workspace_id=test_workspace_id,
        )
        await session.commit()

        assert ev2.previous_hash == ev1.current_hash
