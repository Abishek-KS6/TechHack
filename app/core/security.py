"""
BrandShield AI - Enterprise Security & RBAC Enforcement Core.
Provides Argon2id password hashing, cryptographic JWT access/refresh token lifecycle,
and strict Role-Based Access Control (RBAC) dependency guards with automated audit ledger logging.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
import base64
import hmac
import os
from typing import Annotated, Any, Optional
import uuid

from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ForbiddenProblem, UnauthorizedProblem
from app.core.telemetry import get_correlation_id
from app.domain.enums import AuditAction, UserRole
from app.infrastructure.db.models import User
from app.infrastructure.db.session import get_async_session
from app.services.audit_service import AuditService

settings = get_settings()
security_bearer = HTTPBearer(auto_error=False)

# Argon2id Parameters (aligned with OWASP recommendations)
ARGON2_MEMORY_COST_KIB = 65536  # 64 MiB
ARGON2_TIME_COST = 1           # 1 iteration
ARGON2_PARALLELISM = 4         # 4 lanes
ARGON2_KEY_LEN = 32            # 32 bytes derived key
ARGON2_SALT_LEN = 16           # 16 bytes salt


# ==============================================================================
# 1. Argon2id Password Hashing & Verification
# ==============================================================================

def hash_password(plain_password: str) -> str:
    """
    Computes cryptographically resilient Argon2id password hash in standard PHC string format:
    $argon2id$v=19$m=65536,t=1,p=4$<salt_b64>$<key_b64>
    """
    salt = os.urandom(ARGON2_SALT_LEN)
    kdf = Argon2id(
        salt=salt,
        length=ARGON2_KEY_LEN,
        iterations=ARGON2_TIME_COST,
        lanes=ARGON2_PARALLELISM,
        memory_cost=ARGON2_MEMORY_COST_KIB,
    )
    derived_key = kdf.derive(plain_password.encode("utf-8"))

    salt_b64 = base64.b64encode(salt).decode("ascii")
    key_b64 = base64.b64encode(derived_key).decode("ascii")

    return f"$argon2id$v=19$m={ARGON2_MEMORY_COST_KIB},t={ARGON2_TIME_COST},p={ARGON2_PARALLELISM}${salt_b64}${key_b64}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies plain text password against Argon2id PHC string representation.
    Employs constant-time comparison to prevent side-channel timing attacks.
    """
    if not hashed_password:
        return False

    try:
        parts = hashed_password.split("$")
        if len(parts) != 6 or parts[1] != "argon2id":
            return False

        # Parse memory, time, and parallelism parameters
        param_dict = dict(item.split("=") for item in parts[3].split(","))
        memory_cost = int(param_dict.get("m", ARGON2_MEMORY_COST_KIB))
        iterations = int(param_dict.get("t", ARGON2_TIME_COST))
        lanes = int(param_dict.get("p", ARGON2_PARALLELISM))

        salt = base64.b64decode(parts[4])
        expected_key = base64.b64decode(parts[5])

        kdf = Argon2id(
            salt=salt,
            length=len(expected_key),
            iterations=iterations,
            lanes=lanes,
            memory_cost=memory_cost,
        )
        derived = kdf.derive(plain_password.encode("utf-8"))
        return hmac.compare_digest(derived, expected_key)

    except Exception:
        return False


# ==============================================================================
# 2. JWT Access and Refresh Token Lifecycle
# ==============================================================================

def create_access_token(
    user_id: uuid.UUID | str,
    email: str,
    role: UserRole | str,
    workspace_id: uuid.UUID | str,
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[dict[str, Any]] = None,
) -> str:
    """
    Generates a cryptographically signed JWT access token carrying RBAC role claims.
    """
    role_str = role.value if hasattr(role, "value") else str(role)
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    claims: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role_str,
        "workspace_id": str(workspace_id),
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if additional_claims:
        claims.update(additional_claims)

    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    user_id: uuid.UUID | str,
    email: str,
    role: UserRole | str,
    workspace_id: uuid.UUID | str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generates a cryptographically signed JWT refresh token for session renewals.
    """
    role_str = role.value if hasattr(role, "value") else str(role)
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta if expires_delta is not None else timedelta(days=7))

    claims: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role_str,
        "workspace_id": str(workspace_id),
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_jwt_token(token: str, expected_type: Optional[str] = None) -> dict[str, Any]:
    """
    Decodes and validates signature and expiration of inbound JWT token.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        token_type = payload.get("type")
        if expected_type and token_type != expected_type:
            raise UnauthorizedProblem(
                detail=f"Invalid token type: expected '{expected_type}', got '{token_type}'."
            )
        return payload
    except JWTError as exc:
        raise UnauthorizedProblem(detail=f"Cryptographic validation failed: {str(exc)}") from exc


# ==============================================================================
# 3. RBAC Dependencies & Audit-Integrated RequireRole
# ==============================================================================

async def get_current_user(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Security(security_bearer)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """
    Validates cryptographic signature on inbound JWT and resolves authenticated User entity.
    Supports Authorization Bearer header as well as 'token' query parameter (e.g. for SSE EventSource).
    """
    token: Optional[str] = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif "token" in request.query_params:
        token = request.query_params.get("token")

    if not token:
        raise UnauthorizedProblem(detail="Authentication credentials were not provided.")
    payload = decode_jwt_token(token, expected_type="access")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise UnauthorizedProblem(detail="Token payload missing subject identifier ('sub').")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise UnauthorizedProblem(detail="Invalid subject UUID in token claims.")

    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise ForbiddenProblem(detail="User account is inactive, revoked, or non-existent.")

    return user


class RequireRole:
    """
    FastAPI dependency enforcing strict Role-Based Access Control (RBAC).
    If an actor attempts unauthorized access, automatically commits an immutable
    security event to the cryptographic audit_ledger and raises an RFC 7807 Forbidden error.
    """

    def __init__(self, *allowed_roles: UserRole | str | Sequence[UserRole | str]) -> None:
        flat_roles: list[UserRole] = []
        for role_entry in allowed_roles:
            if isinstance(role_entry, (list, tuple, set)):
                for r in role_entry:
                    flat_roles.append(UserRole(r) if isinstance(r, str) else r)
            else:
                flat_roles.append(UserRole(role_entry) if isinstance(role_entry, str) else role_entry)

        self.allowed_roles: list[UserRole] = flat_roles

    async def __call__(
        self,
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_async_session)],
    ) -> User:
        """
        Evaluates current user role against allowed RBAC hierarchy.
        Logs violations to audit_ledger on unauthorized attempts.
        """
        if current_user.role not in self.allowed_roles:
            required_role_values = [r.value for r in self.allowed_roles]
            user_role_value = (
                current_user.role.value
                if hasattr(current_user.role, "value")
                else str(current_user.role)
            )

            # Record unauthorized breach attempt into tamper-evident audit ledger
            try:
                client_ip = request.client.host if request.client else "unknown"
                user_agent = request.headers.get("user-agent", "unknown")
                cid = get_correlation_id()

                await AuditService.record_event(
                    session=session,
                    action=AuditAction.UNAUTHORIZED_ACCESS_ATTEMPT,
                    workspace_id=current_user.workspace_id,
                    actor_id=current_user.id,
                    payload={
                        "attempted_path": request.url.path,
                        "http_method": request.method,
                        "actor_role": user_role_value,
                        "required_roles": required_role_values,
                        "client_ip": client_ip,
                        "user_agent": user_agent,
                        "correlation_id": cid,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                await session.commit()
            except Exception:
                # Do not suppress authorization denial if logging encounters errors
                pass

            raise ForbiddenProblem(
                detail=(
                    f"Access denied: operation requires one of roles: {required_role_values}. "
                    f"Current role: '{user_role_value}'."
                ),
                required_roles=required_role_values,
                current_role=user_role_value,
            )

        return current_user


# Alias for backward compatibility
require_role = RequireRole
