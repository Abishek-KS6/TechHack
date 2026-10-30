"""
BrandShield AI - Authentication & Cryptographic Session Router.
Handles Argon2id user registration, JWT token generation, token refresh cycles,
and current user profile resolution with full cryptographic audit logging.
"""

from datetime import datetime, timezone
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictProblem, NotFoundProblem, UnauthorizedProblem
from app.core.security import (
    RequireRole,
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.domain.enums import AuditAction, UserRole
from app.domain.schemas.user import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserRead,
    UserRegisterRequest,
)
from app.infrastructure.db.models import User, Workspace
from app.infrastructure.db.session import get_async_session
from app.services.audit_service import AuditService

router = APIRouter()
settings = get_settings()


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a new tenant user (Admin Only)",
    description="Secure user provisioning restricted to authenticated Administrators. Public registration is disabled.",
)
async def register_user(
    payload: UserRegisterRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_admin: Annotated[User, Depends(RequireRole(UserRole.ADMINISTRATOR))],
) -> User:
    """
    Provisions a new tenant actor with Argon2id password hashing and audit chain commitment.
    Strictly restricted to authorized administrators.
    """
    # Resolve or provision tenant workspace
    workspace: Workspace | None = None
    if payload.workspace_id:
        workspace = await session.get(Workspace, payload.workspace_id)
        if not workspace:
            raise NotFoundProblem(
                detail=f"Workspace with ID {payload.workspace_id} not found.",
                resource_type="Workspace",
                resource_id=str(payload.workspace_id),
            )
    else:
        # Default or provision workspace by slug/name
        ws_slug = payload.workspace_slug or f"ws-{uuid.uuid4().hex[:8]}"
        ws_name = payload.workspace_name or "Default Workspace"
        existing_ws_query = select(Workspace).where(Workspace.slug == ws_slug)
        res = await session.execute(existing_ws_query)
        workspace = res.scalar_one_or_none()
        if not workspace:
            workspace = Workspace(name=ws_name, slug=ws_slug)
            session.add(workspace)
            await session.flush()
            await AuditService.record_event(
                session=session,
                action=AuditAction.WORKSPACE_CREATED,
                workspace_id=workspace.id,
                payload={"workspace_id": str(workspace.id), "slug": ws_slug, "name": ws_name},
            )

    # Check for existing user with identical email within workspace
    existing_user_query = select(User).where(
        User.workspace_id == workspace.id,
        User.email == payload.email,
    )
    existing_res = await session.execute(existing_user_query)
    if existing_res.scalar_one_or_none():
        raise ConflictProblem(
            detail=f"User with email '{payload.email}' already exists in this workspace.",
        )

    # Compute Argon2id hash
    hashed_pwd = hash_password(payload.password)

    new_user = User(
        workspace_id=workspace.id,
        email=payload.email,
        hashed_password=hashed_pwd,
        full_name=payload.full_name,
        role=payload.role,
        is_active=True,
    )
    session.add(new_user)
    await session.flush()

    # Commit event to cryptographic audit ledger
    await AuditService.record_event(
        session=session,
        action=AuditAction.USER_REGISTERED,
        workspace_id=workspace.id,
        actor_id=new_user.id,
        payload={
            "user_id": str(new_user.id),
            "email": new_user.email,
            "role": new_user.role.value if hasattr(new_user.role, "value") else str(new_user.role),
            "registered_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await session.commit()
    await session.refresh(new_user)
    return new_user


@router.get(
    "/users",
    response_model=list[UserRead],
    status_code=status.HTTP_200_OK,
    summary="List Workspace Users (Administrator Only)",
)
async def list_workspace_users(
    current_admin: Annotated[User, Depends(RequireRole(UserRole.ADMINISTRATOR))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[User]:
    """Retrieves all users in the workspace. Restricted to administrators."""
    res = await session.execute(
        select(User).where(User.workspace_id == current_admin.workspace_id).order_by(User.created_at.desc())
    )
    return list(res.scalars().all())


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Public User Self-Registration & Sign Up",
    description="Registers a new user, assigns them to an enterprise workspace, and returns access tokens for immediate session launch.",
)
async def signup_user(
    payload: UserRegisterRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """
    Self-serve registration for new users. Creates an account with Argon2id password hashing,
    emits audit ledger events, and returns signed JWT tokens for immediate authentication.
    """
    # 1. Resolve workspace (default to first active workspace or provision one)
    workspace: Workspace | None = None
    if payload.workspace_id:
        workspace = await session.get(Workspace, payload.workspace_id)
    if not workspace:
        # Pick default seeded workspace
        ws_res = await session.execute(select(Workspace).limit(1))
        workspace = ws_res.scalar_one_or_none()
    if not workspace:
        ws_slug = f"ws-{uuid.uuid4().hex[:8]}"
        workspace = Workspace(id=uuid.uuid4(), name="Default Workspace", slug=ws_slug)
        session.add(workspace)
        await session.flush()
        await AuditService.record_event(
            session=session,
            action=AuditAction.WORKSPACE_CREATED,
            workspace_id=workspace.id,
            payload={"workspace_id": str(workspace.id), "slug": ws_slug, "name": "Default Workspace"},
        )

    # 2. Check if user already exists
    existing_user_query = select(User).where(User.email == payload.email)
    existing_res = await session.execute(existing_user_query)
    if existing_res.scalar_one_or_none():
        raise ConflictProblem(
            detail=f"An account with email '{payload.email}' already exists. Please sign in instead.",
        )

    # 3. Hash password & create user (Public self-registration creates CREATOR accounts only)
    hashed_pwd = hash_password(payload.password)
    new_user = User(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        email=payload.email,
        hashed_password=hashed_pwd,
        full_name=payload.full_name,
        role=UserRole.CREATOR,
        is_active=True,
    )
    session.add(new_user)
    await session.flush()

    # 4. Record audit event
    await AuditService.record_event(
        session=session,
        action=AuditAction.USER_REGISTERED,
        workspace_id=workspace.id,
        actor_id=new_user.id,
        payload={
            "user_id": str(new_user.id),
            "email": new_user.email,
            "role": new_user.role.value if hasattr(new_user.role, "value") else str(new_user.role),
            "method": "self_service_signup",
        },
    )

    # 5. Issue JWT tokens
    access_token = create_access_token(
        user_id=new_user.id,
        email=new_user.email,
        role=new_user.role,
        workspace_id=new_user.workspace_id,
    )
    refresh_token = create_refresh_token(
        user_id=new_user.id,
        email=new_user.email,
        role=new_user.role,
        workspace_id=new_user.workspace_id,
    )

    await session.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserRead.model_validate(new_user),
    )


@router.post("/login", response_model=TokenResponse)
@router.post("/token", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """
    Authenticates user credentials using Argon2id verification and returns signed JWT tokens.
    """
    query = select(User).where(User.email == payload.email)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        # Log failed authentication attempt for intrusion detection
        if user:
            await AuditService.record_event(
                session=session,
                action=AuditAction.USER_LOGIN_FAILED,
                workspace_id=user.workspace_id,
                actor_id=user.id,
                payload={"email": payload.email, "reason": "invalid_credentials"},
            )
            await session.commit()
        raise UnauthorizedProblem(detail="Incorrect email or password.")

    if not user.is_active:
        raise UnauthorizedProblem(detail="Account is inactive or revoked.")

    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=user.workspace_id,
    )
    refresh_token = create_refresh_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=user.workspace_id,
    )

    # Log successful login
    await AuditService.record_event(
        session=session,
        action=AuditAction.USER_LOGIN,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        payload={"email": user.email, "role": user.role.value if hasattr(user.role, "value") else str(user.role)},
    )
    await session.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserRead.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    payload: RefreshTokenRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """
    Exchanges a valid refresh token for a newly issued access token.
    """
    token_data = decode_jwt_token(payload.refresh_token, expected_type="refresh")
    user_id_str = token_data.get("sub")
    if not user_id_str:
        raise UnauthorizedProblem(detail="Invalid refresh token claims.")

    user = await session.get(User, uuid.UUID(user_id_str))
    if not user or not user.is_active:
        raise UnauthorizedProblem(detail="User session invalid or terminated.")

    new_access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=user.workspace_id,
    )
    new_refresh_token = create_refresh_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=user.workspace_id,
    )

    await AuditService.record_event(
        session=session,
        action=AuditAction.TOKEN_REFRESHED,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        payload={"email": user.email},
    )
    await session.commit()

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
async def get_current_actor(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Resolves the authenticated actor identity and associated workspace bounds.
    """
    return current_user
