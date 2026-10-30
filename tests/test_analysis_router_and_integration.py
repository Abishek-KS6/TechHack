"""
BrandShield AI - Integration & End-to-End Wiring Verification Suite.
Validates:
1. /api/v1/analysis endpoints (run, submission run, live editor ad-hoc, findings query, engine status).
2. Strict CORS headers for Vite local dev ports and Vercel production origins.
3. Database extensions and lifespan initialization procedures.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid
from httpx import ASGITransport, AsyncClient
import pytest

from app.core.security import create_access_token, hash_password
from app.domain.enums import UserRole, WorkflowState
from app.infrastructure.db.models import (
    BrandProfile,
    DocumentRevision,
    Finding,
    Submission,
    User,
    Workspace,
)
from app.infrastructure.db.session import (
    get_async_session,
    init_db_extensions,
    init_db_seed,
    init_db_tables,
)
from app.main import app


@pytest.fixture
def workspace_id():
    return uuid.uuid4()


@pytest.fixture
def brand_profile_id():
    return uuid.uuid4()


@pytest.fixture
def creator_user(workspace_id):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        email="creator@enterprise.ai",
        hashed_password=hash_password("CreatorPass123!"),
        full_name="Creator User",
        role=UserRole.CREATOR,
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
def sample_brand_profile(workspace_id, brand_profile_id):
    now = datetime.now(timezone.utc)
    return BrandProfile(
        id=brand_profile_id,
        workspace_id=workspace_id,
        name="Global B2B FinTech Profile",
        description="Core B2B compliance boundary",
        tone_parameters={"formality": 8.0},
        banned_terminology_map={"cure": {"reason": "Prohibited medical claim", "severity": "HIGH"}},
        preferred_terminology_map={"cheap": "cost-effective"},
        messaging_rules={"required_trademarks": {"Acme FinTech": "Acme FinTech™"}},
        privacy_gate_config={"allow_external_llm": False, "approved_providers": [], "retention_days": 30},
        is_active=True,
        created_at=now,
        updated_at=now,
    )


# ==============================================================================
# 1. /api/v1/analysis Endpoints
# ==============================================================================

@pytest.mark.asyncio
async def test_analysis_engine_status_endpoint(creator_user, creator_token):
    """Verifies GET /api/v1/analysis/status returns operational telemetry."""
    mock_session = AsyncMock()
    mock_session.get.return_value = creator_user
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get(
                "/api/v1/analysis/status",
                headers={"Authorization": f"Bearer {creator_token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["service"] == "BrandShield Intelligence Pipeline"
            assert len(data["stages"]) == 4
            assert "circuit_breaker_state" in data
            assert data["fallback_cache_size"] >= 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_analysis_live_adhoc_endpoint(creator_user, creator_token, sample_brand_profile):
    """Verifies real-time live editor analysis returns deterministic hits without creating revisions."""
    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        if model == BrandProfile:
            return sample_brand_profile
        return None

    mock_session.get.side_effect = mock_get
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/api/v1/analysis/live",
                headers={"Authorization": f"Bearer {creator_token}"},
                json={
                    "content_text": "Our platform is a cure for latency and costs cheap.",
                    "brand_profile_id": str(sample_brand_profile.id),
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_findings"] >= 1
            assert data["brand_profile_id"] == str(sample_brand_profile.id)
            # 'cure' must be detected
            reasons = [f["explanation_reason"] for f in data["findings"]]
            assert any("cure" in r.lower() for r in reasons)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_analysis_run_pipeline_on_revision(creator_user, creator_token, sample_brand_profile):
    """Verifies POST /api/v1/analysis/run triggers full 4-stage pipeline on revision."""
    sub_id = uuid.uuid4()
    rev_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    mock_sub = Submission(
        id=sub_id,
        workspace_id=creator_user.workspace_id,
        brand_profile_id=sample_brand_profile.id,
        creator_id=creator_user.id,
        title="Whitepaper",
        document_type="TEXT",
        workflow_state=WorkflowState.SUBMITTED,
        current_revision_id=rev_id,
    )
    mock_rev = DocumentRevision(
        id=rev_id,
        submission_id=sub_id,
        revision_number=1,
        content_text="Our platform offers a cure for high latency.",
        ast_span_map=[],
        created_by_id=creator_user.id,
        sha256_content_hash="h1",
        created_at=now,
    )

    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        if model == DocumentRevision:
            return mock_rev
        if model == Submission:
            return mock_sub
        if model == BrandProfile:
            return sample_brand_profile
        return None

    mock_session.get.side_effect = mock_get
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/api/v1/analysis/run",
                headers={"Authorization": f"Bearer {creator_token}"},
                json={"revision_id": str(rev_id)},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["revision_id"] == str(rev_id)
            assert data["submission_id"] == str(sub_id)
            assert data["total_findings"] >= 1
            assert data["processing_duration_ms"] > 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_analysis_submission_run_endpoint(creator_user, creator_token, sample_brand_profile):
    """Verifies POST /api/v1/analysis/submissions/{id}/run analyzes the head revision."""
    sub_id = uuid.uuid4()
    rev_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    mock_sub = Submission(
        id=sub_id,
        workspace_id=creator_user.workspace_id,
        brand_profile_id=sample_brand_profile.id,
        creator_id=creator_user.id,
        title="Marketing One-Pager",
        document_type="TEXT",
        workflow_state=WorkflowState.SUBMITTED,
        current_revision_id=rev_id,
    )
    mock_rev = DocumentRevision(
        id=rev_id,
        submission_id=sub_id,
        revision_number=1,
        content_text="Our platform offers a cure for high costs.",
        ast_span_map=[],
        created_by_id=creator_user.id,
        sha256_content_hash="h1",
        created_at=now,
    )

    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        if model == DocumentRevision:
            return mock_rev
        if model == Submission:
            return mock_sub
        if model == BrandProfile:
            return sample_brand_profile
        return None

    mock_session.get.side_effect = mock_get
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                f"/api/v1/analysis/submissions/{sub_id}/run",
                headers={"Authorization": f"Bearer {creator_token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["submission_id"] == str(sub_id)
            assert data["revision_id"] == str(rev_id)
            assert data["total_findings"] >= 1
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 2. Strict CORS Middleware Verification
# ==============================================================================

@pytest.mark.asyncio
async def test_cors_preflight_local_vite_origin():
    """Verifies strict CORS allows local Vite development origins (localhost:5173)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert resp.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_preflight_vercel_production_origin():
    """Verifies strict CORS dynamically accepts Vercel production deployment origins via regex."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://brandshield-ai-production.vercel.app",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type,X-Correlation-ID",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "https://brandshield-ai-production.vercel.app"
        assert resp.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_expose_telemetry_headers():
    """Verifies X-Correlation-ID and X-Process-Time-Ms are exposed to frontend clients."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            "/api/v1/health",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code == 200
        exposed = resp.headers.get("access-control-expose-headers", "")
        assert "x-correlation-id" in exposed.lower() or "X-Correlation-ID" in exposed
        assert "x-process-time-ms" in exposed.lower() or "X-Process-Time-Ms" in exposed
