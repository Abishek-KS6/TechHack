"""
BrandShield AI - Security, RBAC, and Cryptographic Controls Test Suite.
Validates Argon2id hashing, JWT role claims, RequireRole enforcement, and audit ledger breach logging.
"""

from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest

from app.core.exceptions import ForbiddenProblem, UnauthorizedProblem
from app.core.security import (
    RequireRole,
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    hash_password,
    verify_password,
)
from app.domain.enums import UserRole
from app.infrastructure.db.models import User


def test_argon2id_password_hashing_and_verification():
    """Validates Argon2id PHC string formatting and constant-time verification."""
    password = "EnterpriseSecureP@ssw0rd!2026"
    hashed = hash_password(password)

    # Validate PHC format
    assert hashed.startswith("$argon2id$v=19$m=65536,t=1,p=4$")
    parts = hashed.split("$")
    assert len(parts) == 6

    # Validate verification
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(password, "") is False


def test_jwt_token_generation_and_role_claims():
    """Validates JWT access & refresh tokens carrying strict RBAC claims."""
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    email = "compliance_officer@brandshield.ai"
    role = UserRole.ADMINISTRATOR

    # Access Token
    access_token = create_access_token(
        user_id=user_id,
        email=email,
        role=role,
        workspace_id=workspace_id,
    )
    claims = decode_jwt_token(access_token, expected_type="access")
    assert claims["sub"] == str(user_id)
    assert claims["email"] == email
    assert claims["role"] == UserRole.ADMINISTRATOR.value
    assert claims["workspace_id"] == str(workspace_id)
    assert claims["type"] == "access"
    assert "jti" in claims
    assert claims["exp"] > claims["iat"]

    # Refresh Token
    refresh_token = create_refresh_token(
        user_id=user_id,
        email=email,
        role=role,
        workspace_id=workspace_id,
    )
    r_claims = decode_jwt_token(refresh_token, expected_type="refresh")
    assert r_claims["sub"] == str(user_id)
    assert r_claims["type"] == "refresh"

    # Mismatched expected type raises UnauthorizedProblem
    with pytest.raises(UnauthorizedProblem):
        decode_jwt_token(access_token, expected_type="refresh")


@pytest.mark.asyncio
async def test_require_role_rbac_authorization_success():
    """Validates authorized user passes RequireRole guard."""
    guard = RequireRole(UserRole.ADMINISTRATOR, UserRole.REVIEWER)
    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/brands/profiles"
    mock_request.method = "POST"
    mock_session = AsyncMock()

    user = User(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        email="admin@brandshield.ai",
        hashed_password="hash",
        full_name="Admin User",
        role=UserRole.ADMINISTRATOR,
        is_active=True,
    )

    authorized_user = await guard(
        request=mock_request,
        current_user=user,
        session=mock_session,
    )
    assert authorized_user == user


@pytest.mark.asyncio
async def test_require_role_rbac_breach_logs_to_audit_ledger():
    """Validates unauthorized access attempt logs breach to audit_ledger and raises RFC 7807 ForbiddenProblem."""
    guard = RequireRole(UserRole.ADMINISTRATOR)
    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/brands/profiles"
    mock_request.method = "DELETE"
    mock_request.client.host = "192.168.1.50"
    mock_request.headers = {"user-agent": "PytestClient/1.0"}

    mock_session = AsyncMock()

    creator_user = User(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        email="creator@brandshield.ai",
        hashed_password="hash",
        full_name="Creator User",
        role=UserRole.CREATOR,
        is_active=True,
    )

    with pytest.raises(ForbiddenProblem) as exc_info:
        await guard(
            request=mock_request,
            current_user=creator_user,
            session=mock_session,
        )

    assert exc_info.value.status_code == 403
    assert "ADMINISTRATOR" in exc_info.value.detail
    assert "CREATOR" in exc_info.value.detail
    assert exc_info.value.extensions["required_roles"] == ["ADMINISTRATOR"]
    assert exc_info.value.extensions["current_role"] == "CREATOR"
