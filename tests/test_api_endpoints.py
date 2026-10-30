"""
BrandShield AI - API Endpoints Verification Suite.
Tests /api/v1/auth, /api/v1/brands, and /api/v1/governance/audit-verify routes with RBAC enforcement.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid
from httpx import ASGITransport, AsyncClient
import pytest

from app.core.security import create_access_token, hash_password
from app.domain.enums import UserRole
from app.infrastructure.db.models import BrandProfile, User
from app.infrastructure.db.session import get_async_session
from app.main import app


@pytest.fixture
def mock_db_session():
    """Provides a mocked AsyncSession for dependency override."""
    session = AsyncMock()
    return session


@pytest.fixture
def admin_user():
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        email="admin@enterprise.ai",
        hashed_password=hash_password("SuperSecretAdmin123!"),
        full_name="Enterprise Administrator",
        role=UserRole.ADMINISTRATOR,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def creator_user(admin_user: User):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        workspace_id=admin_user.workspace_id,
        email="creator@enterprise.ai",
        hashed_password=hash_password("CreatorPass123!"),
        full_name="Content Creator",
        role=UserRole.CREATOR,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def admin_token(admin_user: User):
    return create_access_token(
        user_id=admin_user.id,
        email=admin_user.email,
        role=admin_user.role,
        workspace_id=admin_user.workspace_id,
    )


@pytest.fixture
def creator_token(creator_user: User):
    return create_access_token(
        user_id=creator_user.id,
        email=creator_user.email,
        role=creator_user.role,
        workspace_id=creator_user.workspace_id,
    )


@pytest.mark.asyncio
async def test_auth_me_endpoint_success(admin_user: User, admin_token: str, mock_db_session: AsyncMock):
    """Verifies /api/v1/auth/me resolves authenticated user identity."""
    mock_db_session.get.return_value = admin_user
    app.dependency_overrides[get_async_session] = lambda: mock_db_session

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["email"] == admin_user.email
            assert data["role"] == UserRole.ADMINISTRATOR.value
            assert resp.headers.get("X-Correlation-ID") is not None
            assert resp.headers.get("X-Process-Time-Ms") is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_brands_profiles_forbidden_for_creator(creator_user: User, creator_token: str, mock_db_session: AsyncMock):
    """Verifies that non-ADMINISTRATOR role is blocked with 403 on brands CRUD."""
    mock_db_session.get.return_value = creator_user
    app.dependency_overrides[get_async_session] = lambda: mock_db_session

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/brands/profiles",
                headers={"Authorization": f"Bearer {creator_token}"},
            )
            assert resp.status_code == 403
            assert resp.headers["content-type"] == "application/problem+json"
            err = resp.json()
            assert err["type"] == "https://brandshield.ai/errors/forbidden"
            assert "ADMINISTRATOR" in err["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_brands_profiles_crud_allowed_for_admin(admin_user: User, admin_token: str, mock_db_session: AsyncMock):
    """Verifies ADMINISTRATOR can successfully list brand profiles."""
    mock_db_session.get.return_value = admin_user

    mock_profile = BrandProfile(
        id=uuid.uuid4(),
        workspace_id=admin_user.workspace_id,
        name="Global B2B SaaS",
        description="Core B2B profile",
        tone_parameters={"formality": 8},
        banned_terminology_map={},
        preferred_terminology_map={},
        messaging_rules={},
        privacy_gate_config={"allow_external_llm": False, "approved_providers": [], "retention_days": 30},
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_profile]
    mock_db_session.execute.return_value = mock_result

    app.dependency_overrides[get_async_session] = lambda: mock_db_session

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/brands/profiles",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["name"] == "Global B2B SaaS"
            assert data[0]["privacy_gate_config"]["allow_external_llm"] is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_brands_privacy_gate_config_endpoint(admin_user: User, admin_token: str, mock_db_session: AsyncMock):
    """Verifies getting and updating privacy gate configuration."""
    profile_id = uuid.uuid4()
    mock_profile = BrandProfile(
        id=profile_id,
        workspace_id=admin_user.workspace_id,
        name="Security First Brand",
        description="Profiles with strict zero-trust",
        tone_parameters={},
        banned_terminology_map={},
        preferred_terminology_map={},
        messaging_rules={},
        privacy_gate_config={
            "allow_external_llm": False,
            "approved_providers": ["AWS Bedrock", "Azure OpenAI"],
            "contract_verified_at": None,
            "retention_days": 14,
        },
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    async def mock_get(model, ident):
        if model == User:
            return admin_user
        if model == BrandProfile:
            return mock_profile
        return None

    mock_db_session.get.side_effect = mock_get
    app.dependency_overrides[get_async_session] = lambda: mock_db_session

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # GET privacy gate
            resp = await client.get(
                f"/api/v1/brands/profiles/{profile_id}/privacy-gate",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert resp.status_code == 200
            cfg = resp.json()
            assert cfg["retention_days"] == 14
            assert cfg["allow_external_llm"] is False

            # PUT update privacy gate
            update_resp = await client.put(
                f"/api/v1/brands/profiles/{profile_id}/privacy-gate",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"allow_external_llm": True, "retention_days": 60},
            )
            assert update_resp.status_code == 200
            new_cfg = update_resp.json()
            assert new_cfg["allow_external_llm"] is True
            assert new_cfg["retention_days"] == 60
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_governance_audit_verify_endpoint(admin_user: User, admin_token: str, mock_db_session: AsyncMock):
    """Verifies /api/v1/governance/audit-verify endpoint mathematically validates the chain."""
    mock_db_session.get.return_value = admin_user

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result

    app.dependency_overrides[get_async_session] = lambda: mock_db_session

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/governance/audit-verify",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_valid"] is True
            assert "genesis valid" in data["verification_message"].lower() or "sound" in data["verification_message"].lower()
    finally:
        app.dependency_overrides.clear()
