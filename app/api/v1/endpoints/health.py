"""
BrandShield AI - Health and Readiness Probes.
"""

from typing import Any
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import check_db_health, get_async_session

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, str]:
    """Lightweight liveness probe."""
    return {"status": "ok", "service": "BrandShield AI"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """Readiness probe validating database connectivity and pgvector support."""
    db_status = await check_db_health(session)
    return {
        "service": "BrandShield AI",
        "database": db_status,
    }
