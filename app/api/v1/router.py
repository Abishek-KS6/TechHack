"""
BrandShield AI - API v1 Master Router.
Aggregates enterprise authentication, brand administration, document ingestion, governance, and verification sub-routers.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit,
    brand_profiles,
    facts,
    findings,
    health,
)
from app.api.v1.routers import (
    analysis,
    auth,
    brands,
    governance,
    settings,
    submissions,
    system,
    workflow,
)

api_router = APIRouter()

# Core Infrastructure & Probes
api_router.include_router(health.router, tags=["Health & Probes"])
api_router.include_router(system.router, prefix="/system", tags=["System Diagnostics & Introspection"])
api_router.include_router(settings.router, prefix="/settings", tags=["Settings & Review Rules"])

# Security & Authentication
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication & Session"])

# Enterprise Administration & Brand Governance
api_router.include_router(brands.router, prefix="/brands", tags=["Enterprise Brands Administration"])

# Workflow, Revision Engine & Human Review (mounted before submissions router so /revisions/diff is matched before /{revision_number})
api_router.include_router(workflow.router, prefix="/workflow", tags=["Workflow Lifecycle"])
api_router.include_router(workflow.router, prefix="/submissions", tags=["Workflow, Revision Engine & Human Review"])

# Document Ingestion, Revision DAG & Review Decisions
api_router.include_router(submissions.router, prefix="/submissions", tags=["Submissions, Ingestion & Revision DAG"])

# Intelligence Analysis Pipeline & Confidence Triage
api_router.include_router(analysis.router, prefix="/analysis", tags=["Intelligence Analysis & Triage"])

# Cryptographic Governance & Audit Verification
api_router.include_router(governance.router, prefix="/governance", tags=["Cryptographic Governance & Audit Verification"])

# Findings, Facts & Audit Endpoints
api_router.include_router(brand_profiles.router, prefix="/brand-profiles", tags=["Brand Profiles & Governance"])
api_router.include_router(facts.router, prefix="/facts", tags=["Approved Facts & Staleness Engine"])
api_router.include_router(findings.router, prefix="/findings", tags=["Findings & Triage"])
api_router.include_router(audit.router, prefix="/audit", tags=["Cryptographic Audit Ledger"])
