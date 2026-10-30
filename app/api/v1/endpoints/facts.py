"""
BrandShield AI - Substantiated Facts & Temporal Staleness Endpoints.
"""

from datetime import datetime, timezone
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_role
from app.domain.enums import UserRole
from app.domain.schemas.fact import ApprovedFactCreate, ApprovedFactRead
from app.infrastructure.db.models import ApprovedFact, User
from app.infrastructure.db.session import get_async_session

router = APIRouter()


@router.post("/", response_model=ApprovedFactRead, status_code=status.HTTP_201_CREATED)
async def create_approved_fact(
    payload: ApprovedFactCreate,
    current_user: Annotated[User, Depends(require_role([UserRole.REVIEWER, UserRole.ADMINISTRATOR]))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ApprovedFact:
    """Ingests a verified fact with strict expiry dates and 1536-dim vector embedding."""
    fact = ApprovedFact(
        workspace_id=payload.workspace_id,
        brand_profile_id=payload.brand_profile_id,
        fact_statement=payload.fact_statement,
        original_source_url=payload.original_source_url,
        evidence_excerpt=payload.evidence_excerpt,
        verification_date=payload.verification_date,
        expiry_date=payload.expiry_date,
        responsible_owner_id=payload.responsible_owner_id,
        embedding=payload.embedding,
    )
    session.add(fact)
    await session.flush()
    return fact


@router.get("/stale", response_model=list[ApprovedFactRead])
async def list_stale_facts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[ApprovedFact]:
    """Retrieves all expired facts triggering automated re-verification sweeps."""
    now = datetime.now(timezone.utc)
    query = (
        select(ApprovedFact)
        .where(
            ApprovedFact.workspace_id == current_user.workspace_id,
            ApprovedFact.expiry_date <= now,
            ApprovedFact.is_active == True,  # noqa: E712
        )
        .order_by(ApprovedFact.expiry_date.asc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())


@router.post("/search/semantic", response_model=list[ApprovedFactRead])
async def search_facts_semantic(
    query_embedding: list[float],
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    limit: int = Query(default=5, ge=1, le=20),
) -> list[ApprovedFact]:
    """HNSW-accelerated semantic vector search for verified facts."""
    if len(query_embedding) != 1536:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Query embedding must be exactly 1536 dimensions, got {len(query_embedding)}",
        )

    now = datetime.now(timezone.utc)
    # Cosine distance ordering utilizing pgvector index
    query = (
        select(ApprovedFact)
        .where(
            ApprovedFact.workspace_id == current_user.workspace_id,
            ApprovedFact.expiry_date > now,  # Exclude expired facts from active claim grounding
            ApprovedFact.is_active == True,  # noqa: E712
        )
        .order_by(ApprovedFact.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())
