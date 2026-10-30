"""
BrandShield AI - Brand Profiles and Guidelines Governance Endpoints.
"""

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, require_role
from app.domain.enums import UserRole
from app.domain.schemas.brand_profile import (
    BrandGuidelineCreate,
    BrandGuidelineRead,
    BrandProfileCreate,
    BrandProfileRead,
)
from app.infrastructure.db.models import BrandGuideline, BrandProfile, User
from app.infrastructure.db.session import get_async_session

router = APIRouter()


@router.post("/", response_model=BrandProfileRead, status_code=status.HTTP_201_CREATED)
async def create_brand_profile(
    payload: BrandProfileCreate,
    current_user: Annotated[User, Depends(require_role([UserRole.ADMINISTRATOR]))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BrandProfile:
    """Creates a new brand profile with configurable tone, banned terms, and privacy gate."""
    profile = BrandProfile(
        workspace_id=payload.workspace_id,
        name=payload.name,
        description=payload.description,
        tone_parameters=payload.tone_parameters,
        banned_terminology_map=payload.banned_terminology_map,
        preferred_terminology_map=payload.preferred_terminology_map,
        messaging_rules=payload.messaging_rules,
        privacy_gate_config=payload.privacy_gate_config.model_dump(),
    )
    session.add(profile)
    await session.flush()
    return profile


@router.get("/{profile_id}", response_model=BrandProfileRead)
async def get_brand_profile(
    profile_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BrandProfile:
    """Retrieves brand profile governance specification by ID."""
    profile = await session.get(BrandProfile, profile_id)
    if not profile or profile.workspace_id != current_user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand profile not found in your workspace.",
        )
    return profile


@router.post(
    "/{profile_id}/guidelines",
    response_model=BrandGuidelineRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_brand_guideline(
    profile_id: uuid.UUID,
    payload: BrandGuidelineCreate,
    current_user: Annotated[User, Depends(require_role([UserRole.ADMINISTRATOR]))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BrandGuideline:
    """Adds a regulatory or brand directive clause with 1536-dim vector embedding."""
    profile = await session.get(BrandProfile, profile_id)
    if not profile or profile.workspace_id != current_user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand profile not found.",
        )

    guideline = BrandGuideline(
        brand_profile_id=profile_id,
        clause_identifier=payload.clause_identifier,
        clause_text=payload.clause_text,
        category=payload.category,
        severity=payload.severity,
        embedding=payload.embedding,
    )
    session.add(guideline)
    await session.flush()
    return guideline
