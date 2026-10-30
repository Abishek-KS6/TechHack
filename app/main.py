"""
BrandShield AI - Production Application Factory
Enterprise Brand Governance & Content Verification Platform.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.idempotency import IdempotencyMiddleware
from app.core.telemetry import TelemetryMiddleware, setup_telemetry_logging
from app.infrastructure.db.session import (
    close_db_connection,
    init_db_extensions,
    init_db_seed,
    init_db_tables,
)

# Initialize JSON telemetry logging
logger = setup_telemetry_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle manager:
    - Automatically executes CREATE EXTENSION IF NOT EXISTS vector; and pg_trgm; on PostgreSQL startup.
    - Idempotently creates and verifies all database tables and native enum types.
    - Runs the idempotent seed script (seed.py) if the database is unpopulated.
    - Disposes database connection pool cleanly on graceful shutdown.
    """
    logger.info("Starting up %s (Environment: %s)...", settings.PROJECT_NAME, settings.ENVIRONMENT)
    try:
        # 1. Ensure required PostgreSQL extensions: vector, pg_trgm, uuid-ossp
        await init_db_extensions()
        # 2. Idempotently create/verify database tables
        await init_db_tables()
        # 3. Check for empty database and run idempotent seeder
        await init_db_seed()
    except Exception as exc:
        logger.warning(
            "Could not automatically initialize PostgreSQL extensions/tables during startup (check connection/permissions): %s",
            exc,
        )

    yield

    logger.info("Shutting down %s...", settings.PROJECT_NAME)
    await close_db_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="Intelligent Enterprise Brand Governance, Content Verification & Regulatory Audit Perimeter.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enterprise Observability & Correlation ID Middleware
app.add_middleware(TelemetryMiddleware)

# Stripe-Style Idempotency Replay Middleware
app.add_middleware(IdempotencyMiddleware)

# Cross-Origin Resource Sharing (CORS) - Strict configuration for React + Tailwind CSS frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "X-Correlation-ID",
        "Idempotency-Key",
        "Origin",
        "X-Requested-With",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
    ],
    expose_headers=[
        "X-Correlation-ID",
        "X-Process-Time-Ms",
        "X-Cache-Idempotency",
        "Content-Range",
        "Link",
    ],
)

# RFC 7807 Problem Details Global Exception Handlers
register_exception_handlers(app)

# Mount API v1
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """Root platform descriptor."""
    return {
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "api_v1_docs": "/docs",
        "health_check": f"{settings.API_V1_PREFIX}/health",
    }
