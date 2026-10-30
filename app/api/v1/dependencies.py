"""
BrandShield AI - API v1 Security & Dependency Injection Primitives.
Re-exports core security primitives, JWT authentication, and RBAC guards.
"""

from app.core.security import (
    RequireRole,
    get_current_user,
    require_role,
    security_bearer,
)

__all__ = [
    "RequireRole",
    "get_current_user",
    "require_role",
    "security_bearer",
]
