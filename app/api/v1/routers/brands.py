"""
BrandShield AI - Enterprise Brand Governance & Policy Configuration Router.
Provides full CRUD capabilities for ADMINISTRATOR actors to govern Brand Profiles,
Guidelines, Approved Facts (with temporal validity & provenance links), and Zero-Trust Privacy Gates.
"""

from datetime import datetime, timezone
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundProblem, ValidationErrorProblem
from app.core.security import RequireRole, get_current_user
from app.domain.enums import AuditAction, UserRole
from app.domain.schemas.asset import (
    ApprovedBrandAssetCreate,
    ApprovedBrandAssetRead,
    AssetCatalogMatchingResponse,
)
from app.domain.schemas.brand_profile import (
    BrandGuidelineCreate,
    BrandGuidelineRead,
    BrandGuidelineUpdate,
    BrandProfileCreate,
    BrandProfileRead,
    BrandProfileUpdate,
    PrivacyGateConfigSchema,
    PrivacyGateConfigUpdate,
)
from app.domain.schemas.fact import (
    ApprovedFactCreate,
    ApprovedFactRead,
    ApprovedFactUpdate,
)
from app.infrastructure.db.models import (
    ApprovedFact,
    BrandGuideline,
    BrandProfile,
    User,
)
from app.infrastructure.db.session import get_async_session
from app.services.analysis.asset_matcher import VisualAssetMatcher
from app.services.audit_service import AuditService

router = APIRouter()

# Enforce strict ADMINISTRATOR RBAC across all routes
AdminUser = Annotated[User, Depends(RequireRole(UserRole.ADMINISTRATOR))]


# ==============================================================================
# 1. Brand Profiles CRUD
# ==============================================================================

@router.post("/profiles", response_model=BrandProfileRead, status_code=status.HTTP_201_CREATED)
async def create_brand_profile(
    payload: BrandProfileCreate,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BrandProfile:
    """Creates a new brand profile specifying corporate tone, banned vocabulary, and privacy policies."""
    profile = BrandProfile(
        workspace_id=payload.workspace_id or admin.workspace_id,
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

    await AuditService.record_event(
        session=session,
        action=AuditAction.BRAND_PROFILE_CREATED,
        workspace_id=profile.workspace_id,
        actor_id=admin.id,
        payload={"profile_id": str(profile.id), "name": profile.name},
    )
    await session.commit()
    await session.refresh(profile)
    return profile


@router.get("/active-profile", response_model=BrandProfileRead)
async def get_active_brand_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BrandProfile:
    """Retrieves active brand profile for current user's workspace, accessible to all workspace roles."""
    stmt = (
        select(BrandProfile)
        .where(BrandProfile.workspace_id == current_user.workspace_id)
        .order_by(BrandProfile.created_at.asc())
    )
    res = await session.execute(stmt)
    profile = res.scalars().first()
    if not profile:
        raise NotFoundProblem(
            detail="No brand profile found for workspace.",
            resource_type="BrandProfile",
        )
    return profile


@router.get("/profiles", response_model=list[BrandProfileRead])
async def list_brand_profiles(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[BrandProfile]:
    """Retrieves all active and archived brand profiles belonging to user's tenant workspace."""
    query = (
        select(BrandProfile)
        .where(BrandProfile.workspace_id == current_user.workspace_id)
        .order_by(BrandProfile.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/profiles/{profile_id}", response_model=BrandProfileRead)
async def get_brand_profile(
    profile_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BrandProfile:
    """Retrieves detailed brand profile governance specification by unique ID."""
    profile = await session.get(BrandProfile, profile_id)
    if not profile or profile.workspace_id != current_user.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{profile_id}' not found in workspace.",
            resource_type="BrandProfile",
            resource_id=str(profile_id),
        )
    return profile


@router.put("/profiles/{profile_id}", response_model=BrandProfileRead)
async def update_brand_profile(
    profile_id: uuid.UUID,
    payload: BrandProfileUpdate,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BrandProfile:
    """Updates brand profile tone thresholds, vocabulary maps, or active status."""
    profile = await session.get(BrandProfile, profile_id)
    if not profile or profile.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{profile_id}' not found in workspace.",
            resource_type="BrandProfile",
            resource_id=str(profile_id),
        )

    update_data = payload.model_dump(exclude_unset=True)
    if "privacy_gate_config" in update_data and update_data["privacy_gate_config"] is not None:
        if isinstance(update_data["privacy_gate_config"], dict):
            profile.privacy_gate_config = update_data["privacy_gate_config"]
        elif hasattr(update_data["privacy_gate_config"], "model_dump"):
            profile.privacy_gate_config = update_data["privacy_gate_config"].model_dump()
        del update_data["privacy_gate_config"]

    for key, value in update_data.items():
        setattr(profile, key, value)

    await session.flush()
    await AuditService.record_event(
        session=session,
        action=AuditAction.BRAND_PROFILE_UPDATED,
        workspace_id=profile.workspace_id,
        actor_id=admin.id,
        payload={"profile_id": str(profile.id), "updated_fields": list(payload.model_dump(exclude_unset=True).keys())},
    )
    await session.commit()
    await session.refresh(profile)
    return profile


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand_profile(
    profile_id: uuid.UUID,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Removes a brand profile and cascades deletion of attached guidelines."""
    profile = await session.get(BrandProfile, profile_id)
    if not profile or profile.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{profile_id}' not found in workspace.",
            resource_type="BrandProfile",
            resource_id=str(profile_id),
        )

    await session.delete(profile)
    await AuditService.record_event(
        session=session,
        action=AuditAction.BRAND_PROFILE_DELETED,
        workspace_id=admin.workspace_id,
        actor_id=admin.id,
        payload={"deleted_profile_id": str(profile_id), "name": profile.name},
    )
    await session.commit()


# ==============================================================================
# 2. Brand Guidelines CRUD
# ==============================================================================

@router.post(
    "/profiles/{profile_id}/guidelines",
    response_model=BrandGuidelineRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_brand_guideline(
    profile_id: uuid.UUID,
    payload: BrandGuidelineCreate,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BrandGuideline:
    """Adds a regulatory compliance directive clause with dense 1536-dim vector embedding."""
    profile = await session.get(BrandProfile, profile_id)
    if not profile or profile.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{profile_id}' not found.",
            resource_type="BrandProfile",
            resource_id=str(profile_id),
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

    await AuditService.record_event(
        session=session,
        action=AuditAction.BRAND_GUIDELINE_CREATED,
        workspace_id=profile.workspace_id,
        actor_id=admin.id,
        payload={
            "guideline_id": str(guideline.id),
            "profile_id": str(profile_id),
            "clause_identifier": guideline.clause_identifier,
        },
    )
    await session.commit()
    await session.refresh(guideline)
    return guideline


@router.get("/profiles/{profile_id}/guidelines", response_model=list[BrandGuidelineRead])
async def list_brand_guidelines(
    profile_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[BrandGuideline]:
    """Lists all guideline directives indexed under the designated brand profile."""
    profile = await session.get(BrandProfile, profile_id)
    if not profile or profile.workspace_id != current_user.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{profile_id}' not found.",
            resource_type="BrandProfile",
            resource_id=str(profile_id),
        )

    query = (
        select(BrandGuideline)
        .where(BrandGuideline.brand_profile_id == profile_id)
        .order_by(BrandGuideline.clause_identifier.asc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/guidelines/{guideline_id}", response_model=BrandGuidelineRead)
async def get_brand_guideline(
    guideline_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BrandGuideline:
    """Retrieves an individual guideline directive by ID."""
    guideline = await session.get(BrandGuideline, guideline_id)
    if not guideline:
        raise NotFoundProblem(
            detail=f"Brand guideline '{guideline_id}' not found.",
            resource_type="BrandGuideline",
            resource_id=str(guideline_id),
        )
    # Ensure tenant isolation via parent brand profile
    profile = await session.get(BrandProfile, guideline.brand_profile_id)
    if not profile or profile.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand guideline '{guideline_id}' not found in workspace.",
            resource_type="BrandGuideline",
            resource_id=str(guideline_id),
        )
    return guideline


@router.put("/guidelines/{guideline_id}", response_model=BrandGuidelineRead)
async def update_brand_guideline(
    guideline_id: uuid.UUID,
    payload: BrandGuidelineUpdate,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BrandGuideline:
    """Updates a brand guideline clause, category, severity, or embedding."""
    guideline = await session.get(BrandGuideline, guideline_id)
    if not guideline:
        raise NotFoundProblem(
            detail=f"Brand guideline '{guideline_id}' not found.",
            resource_type="BrandGuideline",
            resource_id=str(guideline_id),
        )
    profile = await session.get(BrandProfile, guideline.brand_profile_id)
    if not profile or profile.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand guideline '{guideline_id}' not found in workspace.",
            resource_type="BrandGuideline",
            resource_id=str(guideline_id),
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(guideline, key, value)

    await session.flush()
    await AuditService.record_event(
        session=session,
        action=AuditAction.BRAND_GUIDELINE_UPDATED,
        workspace_id=admin.workspace_id,
        actor_id=admin.id,
        payload={"guideline_id": str(guideline.id), "clause_identifier": guideline.clause_identifier},
    )
    await session.commit()
    await session.refresh(guideline)
    return guideline


@router.delete("/guidelines/{guideline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand_guideline(
    guideline_id: uuid.UUID,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Removes a brand guideline clause from the semantic retrieval vector space."""
    guideline = await session.get(BrandGuideline, guideline_id)
    if not guideline:
        raise NotFoundProblem(
            detail=f"Brand guideline '{guideline_id}' not found.",
            resource_type="BrandGuideline",
            resource_id=str(guideline_id),
        )
    profile = await session.get(BrandProfile, guideline.brand_profile_id)
    if not profile or profile.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand guideline '{guideline_id}' not found in workspace.",
            resource_type="BrandGuideline",
            resource_id=str(guideline_id),
        )

    await session.delete(guideline)
    await AuditService.record_event(
        session=session,
        action=AuditAction.BRAND_GUIDELINE_DELETED,
        workspace_id=admin.workspace_id,
        actor_id=admin.id,
        payload={"deleted_guideline_id": str(guideline_id), "clause_identifier": guideline.clause_identifier},
    )
    await session.commit()


# ==============================================================================
# 3. Approved Facts CRUD
# ==============================================================================

@router.post("/facts", response_model=ApprovedFactRead, status_code=status.HTTP_201_CREATED)
async def create_approved_fact(
    payload: ApprovedFactCreate,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ApprovedFact:
    """
    Ingests an approved marketing fact substantiated with verification date, expiry window,
    provenance source URL, legal excerpt, and 1536-dim semantic dense embedding.
    """
    if payload.expiry_date <= payload.verification_date:
        raise ValidationErrorProblem(
            detail="Fact validation error: expiry_date must be strictly greater than verification_date."
        )

    # Validate responsible owner exists
    owner = await session.get(User, payload.responsible_owner_id)
    if not owner or owner.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Responsible owner with ID '{payload.responsible_owner_id}' not found in workspace.",
            resource_type="User",
            resource_id=str(payload.responsible_owner_id),
        )

    fact = ApprovedFact(
        workspace_id=admin.workspace_id,
        brand_profile_id=payload.brand_profile_id,
        fact_statement=payload.fact_statement,
        original_source_url=payload.original_source_url,
        evidence_excerpt=payload.evidence_excerpt,
        verification_date=payload.verification_date,
        last_updated_date=datetime.now(timezone.utc),
        expiry_date=payload.expiry_date,
        responsible_owner_id=payload.responsible_owner_id,
        embedding=payload.embedding,
        is_active=True,
    )
    session.add(fact)
    await session.flush()

    await AuditService.record_event(
        session=session,
        action=AuditAction.FACT_CREATED,
        workspace_id=admin.workspace_id,
        actor_id=admin.id,
        payload={
            "fact_id": str(fact.id),
            "fact_statement": fact.fact_statement[:120],
            "expiry_date": fact.expiry_date.isoformat(),
            "source_url": fact.original_source_url,
        },
    )
    await session.commit()
    await session.refresh(fact)
    return fact


@router.get("/facts", response_model=list[ApprovedFactRead])
async def list_approved_facts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    include_stale: bool = Query(default=True, description="Include expired facts"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[ApprovedFact]:
    """Lists approved facts with temporal validity metadata."""
    query = (
        select(ApprovedFact)
        .where(ApprovedFact.workspace_id == current_user.workspace_id)
        .order_by(ApprovedFact.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if not include_stale:
        now = datetime.now(timezone.utc)
        query = query.where(ApprovedFact.expiry_date > now)

    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/facts/{fact_id}", response_model=ApprovedFactRead)
async def get_approved_fact(
    fact_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ApprovedFact:
    """Retrieves an individual approved fact by unique ID."""
    fact = await session.get(ApprovedFact, fact_id)
    if not fact or fact.workspace_id != current_user.workspace_id:
        raise NotFoundProblem(
            detail=f"Approved fact '{fact_id}' not found in workspace.",
            resource_type="ApprovedFact",
            resource_id=str(fact_id),
        )
    return fact


@router.put("/facts/{fact_id}", response_model=ApprovedFactRead)
async def update_approved_fact(
    fact_id: uuid.UUID,
    payload: ApprovedFactUpdate,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ApprovedFact:
    """Updates approved fact verification/expiry dates, evidence excerpts, or active status."""
    fact = await session.get(ApprovedFact, fact_id)
    if not fact or fact.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Approved fact '{fact_id}' not found in workspace.",
            resource_type="ApprovedFact",
            resource_id=str(fact_id),
        )

    update_data = payload.model_dump(exclude_unset=True)

    # Check temporal bounds
    new_v_date = update_data.get("verification_date", fact.verification_date)
    new_e_date = update_data.get("expiry_date", fact.expiry_date)
    if new_e_date <= new_v_date:
        raise ValidationErrorProblem(
            detail="Fact validation error: expiry_date must be strictly greater than verification_date."
        )

    for key, value in update_data.items():
        setattr(fact, key, value)

    fact.last_updated_date = datetime.now(timezone.utc)
    await session.flush()

    await AuditService.record_event(
        session=session,
        action=AuditAction.FACT_UPDATED,
        workspace_id=admin.workspace_id,
        actor_id=admin.id,
        payload={"fact_id": str(fact.id), "updated_fields": list(update_data.keys())},
    )
    await session.commit()
    await session.refresh(fact)
    return fact


@router.delete("/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_approved_fact(
    fact_id: uuid.UUID,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Removes an approved fact claim from the grounding knowledge base."""
    fact = await session.get(ApprovedFact, fact_id)
    if not fact or fact.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Approved fact '{fact_id}' not found in workspace.",
            resource_type="ApprovedFact",
            resource_id=str(fact_id),
        )

    await session.delete(fact)
    await AuditService.record_event(
        session=session,
        action=AuditAction.FACT_DELETED,
        workspace_id=admin.workspace_id,
        actor_id=admin.id,
        payload={"deleted_fact_id": str(fact_id), "fact_statement": fact.fact_statement[:100]},
    )
    await session.commit()


# ==============================================================================
# 4. Zero-Trust Privacy Gate Configuration
# ==============================================================================

@router.get("/profiles/{profile_id}/privacy-gate", response_model=PrivacyGateConfigSchema)
async def get_privacy_gate_config(
    profile_id: uuid.UUID,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PrivacyGateConfigSchema:
    """Retrieves external LLM egress rules and data retention bounds for brand profile."""
    profile = await session.get(BrandProfile, profile_id)
    if not profile or profile.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{profile_id}' not found.",
            resource_type="BrandProfile",
            resource_id=str(profile_id),
        )
    return PrivacyGateConfigSchema(**profile.privacy_gate_config)


@router.put("/profiles/{profile_id}/privacy-gate", response_model=PrivacyGateConfigSchema)
async def configure_privacy_gate(
    profile_id: uuid.UUID,
    payload: PrivacyGateConfigUpdate,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PrivacyGateConfigSchema:
    """
    Configures zero-trust privacy gate perimeter: controls external LLM egress clearance,
    whitelisted enterprise AI providers, and regulatory retention limits.
    """
    profile = await session.get(BrandProfile, profile_id)
    if not profile or profile.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{profile_id}' not found.",
            resource_type="BrandProfile",
            resource_id=str(profile_id),
        )

    current_cfg = dict(profile.privacy_gate_config)
    update_data = payload.model_dump(exclude_unset=True)

    for k, v in update_data.items():
        if v is not None:
            if isinstance(v, datetime):
                current_cfg[k] = v.isoformat()
            else:
                current_cfg[k] = v

    profile.privacy_gate_config = current_cfg
    await session.flush()

    await AuditService.record_event(
        session=session,
        action=AuditAction.PRIVACY_GATE_CONFIGURED,
        workspace_id=admin.workspace_id,
        actor_id=admin.id,
        payload={
            "profile_id": str(profile_id),
            "privacy_gate_config": current_cfg,
        },
    )
    await session.commit()
    await session.refresh(profile)
    return PrivacyGateConfigSchema(**profile.privacy_gate_config)


# ==============================================================================
# 5. Approved Brand Asset Catalog & Visual Comparison
# ==============================================================================

@router.post(
    "/{brand_id}/assets",
    response_model=ApprovedBrandAssetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register Approved Brand Asset in Catalog",
)
async def register_brand_asset(
    brand_id: uuid.UUID,
    payload: ApprovedBrandAssetCreate,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ApprovedBrandAssetRead:
    """
    Registers an official approved brand asset (logo, typography lockup, official graphic)
    in the organization's catalog. These assets serve as the exclusive baseline for
    embedded visual comparison and distortion detection.
    """
    profile = await session.get(BrandProfile, brand_id)
    if not profile or profile.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{brand_id}' not found.",
            resource_type="BrandProfile",
            resource_id=str(brand_id),
        )

    messaging_rules = dict(profile.messaging_rules or {})
    assets_list = list(messaging_rules.get("approved_assets", []))

    asset_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    asset_record = {
        "id": str(asset_id),
        "brand_profile_id": str(brand_id),
        "name": payload.name,
        "asset_type": payload.asset_type,
        "file_name": payload.file_name,
        "dhash": payload.dhash,
        "phash": payload.phash,
        "aspect_ratio": payload.aspect_ratio,
        "width_px": payload.width_px,
        "height_px": payload.height_px,
        "is_deprecated": payload.is_deprecated,
        "deprecated_replacement_asset_id": str(payload.deprecated_replacement_asset_id) if payload.deprecated_replacement_asset_id else None,
        "valid_until": payload.valid_until.isoformat() if payload.valid_until else None,
        "metadata": payload.metadata,
        "created_at": now.isoformat(),
    }
    assets_list.append(asset_record)
    messaging_rules["approved_assets"] = assets_list
    profile.messaging_rules = messaging_rules

    await session.flush()
    await AuditService.record_event(
        session=session,
        action=AuditAction.BRAND_ASSET_REGISTERED,
        workspace_id=admin.workspace_id,
        actor_id=admin.id,
        payload={"brand_id": str(brand_id), "asset_id": str(asset_id), "name": payload.name},
    )
    await session.commit()
    return ApprovedBrandAssetRead(
        id=asset_id,
        brand_profile_id=brand_id,
        name=payload.name,
        asset_type=payload.asset_type,
        file_name=payload.file_name,
        dhash=payload.dhash,
        phash=payload.phash,
        aspect_ratio=payload.aspect_ratio,
        width_px=payload.width_px,
        height_px=payload.height_px,
        is_deprecated=payload.is_deprecated,
        deprecated_replacement_asset_id=payload.deprecated_replacement_asset_id,
        valid_until=payload.valid_until,
        metadata=payload.metadata,
        created_at=now,
    )


@router.get(
    "/{brand_id}/assets",
    response_model=list[ApprovedBrandAssetRead],
    summary="List Organization Approved Brand Assets",
)
async def list_brand_assets(
    brand_id: uuid.UUID,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[ApprovedBrandAssetRead]:
    """
    Lists all officially approved brand assets registered for this profile.
    """
    profile = await session.get(BrandProfile, brand_id)
    if not profile or profile.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{brand_id}' not found.",
            resource_type="BrandProfile",
            resource_id=str(brand_id),
        )

    messaging_rules = profile.messaging_rules or {}
    raw_assets = messaging_rules.get("approved_assets", [])
    results: list[ApprovedBrandAssetRead] = []
    for a in raw_assets:
        try:
            results.append(
                ApprovedBrandAssetRead(
                    id=uuid.UUID(a["id"]),
                    brand_profile_id=uuid.UUID(a["brand_profile_id"]),
                    name=a["name"],
                    asset_type=a.get("asset_type", "LOGO"),
                    file_name=a["file_name"],
                    dhash=a["dhash"],
                    phash=a.get("phash"),
                    aspect_ratio=float(a["aspect_ratio"]),
                    width_px=int(a["width_px"]),
                    height_px=int(a["height_px"]),
                    is_deprecated=bool(a.get("is_deprecated", False)),
                    deprecated_replacement_asset_id=uuid.UUID(a["deprecated_replacement_asset_id"]) if a.get("deprecated_replacement_asset_id") else None,
                    valid_until=datetime.fromisoformat(a["valid_until"]) if a.get("valid_until") else None,
                    metadata=a.get("metadata", {}),
                    created_at=datetime.fromisoformat(a["created_at"]) if a.get("created_at") else datetime.now(timezone.utc),
                )
            )
        except Exception:
            continue
    return results


@router.post(
    "/{brand_id}/assets/match",
    response_model=AssetCatalogMatchingResponse,
    summary="Visual Inspection Against Approved Organizational Assets",
)
async def match_document_assets(
    brand_id: uuid.UUID,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    file: UploadFile = File(...),
) -> AssetCatalogMatchingResponse:
    """
    Inspects embedded raster images in submitted PDF/DOCX or direct image files
    and compares them strictly against the organization's catalog of approved brand assets.
    Flags:
    - UNAPPROVED_ASSET: Image not in approved catalog.
    - STRETCHED_OR_DISTORTED: Approved logo with distorted aspect ratio.
    - OUTDATED_LOGO: Matches an approved asset marked is_deprecated or expired.
    - APPROVED_MATCH: Fully compliant approved asset.
    """
    profile = await session.get(BrandProfile, brand_id)
    if not profile or profile.workspace_id != admin.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{brand_id}' not found.",
            resource_type="BrandProfile",
            resource_id=str(brand_id),
        )

    file_bytes = await file.read()
    messaging_rules = profile.messaging_rules or {}
    catalog = messaging_rules.get("approved_assets", [])

    return VisualAssetMatcher.inspect_document(
        file_bytes=file_bytes,
        filename=file.filename or "upload.bin",
        brand_profile_id=brand_id,
        approved_catalog=catalog,
    )
