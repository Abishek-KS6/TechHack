"""
BrandShield AI Database Infrastructure Layer.
Exposes base declarative metadata, models, and session management.
"""

from app.infrastructure.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.infrastructure.db.models import (
    ApprovedFact,
    AuditLedger,
    BrandGuideline,
    BrandProfile,
    DocumentRevision,
    Finding,
    ReviewDecision,
    Submission,
    User,
    Workspace,
)
from app.infrastructure.db.session import (
    AsyncSessionLocal,
    async_engine,
    check_db_health,
    close_db_connection,
    get_async_session,
    init_db_extensions,
)

__all__ = [
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "Workspace",
    "User",
    "BrandProfile",
    "BrandGuideline",
    "ApprovedFact",
    "Submission",
    "DocumentRevision",
    "Finding",
    "ReviewDecision",
    "AuditLedger",
    "async_engine",
    "AsyncSessionLocal",
    "get_async_session",
    "init_db_extensions",
    "check_db_health",
    "close_db_connection",
]
