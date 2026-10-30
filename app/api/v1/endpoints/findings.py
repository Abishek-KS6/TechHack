"""
BrandShield AI - Findings and Triage Actions Endpoints.
"""

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_role
from app.domain.enums import UserRole
from app.domain.schemas.finding import FindingCreate, FindingRead, FindingUpdateAction
from app.infrastructure.db.models import Finding, User
from app.infrastructure.db.session import get_async_session
from app.services.finding_triage_service import FindingTriageService

router = APIRouter()


@router.post("/", response_model=FindingRead, status_code=status.HTTP_201_CREATED)
async def create_finding(
    payload: FindingCreate,
    current_user: Annotated[User, Depends(require_role([UserRole.REVIEWER, UserRole.ADMINISTRATOR]))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Finding:
    """Ingests finding with automated tri-state triage and stochastic anti-bias sampling."""
    try:
        finding = await FindingTriageService.ingest_finding(
            session=session,
            payload=payload,
            workspace_id=current_user.workspace_id,
        )
        return finding
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/by-revision/{revision_id}", response_model=list[FindingRead])
async def list_findings_by_revision(
    revision_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[Finding]:
    """Retrieves all detection findings associated with a specific immutable revision."""
    query = (
        select(Finding)
        .where(Finding.revision_id == revision_id)
        .order_by(Finding.start_offset.asc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())


@router.patch("/{finding_id}/action", response_model=FindingRead)
async def update_creator_action(
    finding_id: uuid.UUID,
    payload: FindingUpdateAction,
    current_user: Annotated[User, Depends(require_role([UserRole.CREATOR, UserRole.ADMINISTRATOR]))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Finding:
    """Updates author action (ACCEPTED, REJECTED, EDITED) in response to a finding."""
    try:
        finding = await FindingTriageService.update_creator_action(
            session=session,
            finding_id=finding_id,
            actor_id=current_user.id,
            workspace_id=current_user.workspace_id,
            payload=payload,
        )
        return finding
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
