"""
BrandShield AI - Hash-Chained Audit Ledger Inspection & Cryptographic Verification.
"""

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_role
from app.domain.enums import UserRole
from app.domain.schemas.audit import AuditChainVerificationResult, AuditLedgerRead
from app.infrastructure.db.models import AuditLedger, User
from app.infrastructure.db.session import get_async_session
from app.services.audit_service import AuditService

router = APIRouter()


@router.get("/logs", response_model=list[AuditLedgerRead])
async def list_audit_logs(
    current_user: Annotated[User, Depends(require_role([UserRole.ADMINISTRATOR]))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLedger]:
    """Retrieves paginated audit ledger events for the enterprise tenant."""
    query = (
        select(AuditLedger)
        .where(AuditLedger.workspace_id == current_user.workspace_id)
        .order_by(AuditLedger.sequence_id.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


@router.post("/verify-chain", response_model=AuditChainVerificationResult)
async def verify_audit_chain_integrity(
    current_user: Annotated[User, Depends(require_role([UserRole.ADMINISTRATOR]))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AuditChainVerificationResult:
    """
    Executes end-to-end cryptographic SHA-256 verification of the audit chain,
    proving zero database tampering or historical record mutation.
    """
    return await AuditService.verify_chain_integrity(
        session=session,
        workspace_id=current_user.workspace_id,
    )
