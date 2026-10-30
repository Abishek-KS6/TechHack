"""
BrandShield AI - Intelligence Analysis & Triage Router.
Exposes endpoints to:
1. Run the 4-Stage Intelligence Pipeline on immutable document revisions (POST /analysis/run).
2. Trigger automated analysis for an entire submission tip (POST /analysis/submissions/{id}/run).
3. Execute real-time ad-hoc compliance checks for live interactive editor feedback (POST /analysis/live).
4. Inspect triaged findings linked to specific revision nodes (GET /analysis/revisions/{id}/findings).
5. Monitor intelligence engine health, circuit breaker, and demo fallback cache (GET /analysis/status).
"""

from datetime import datetime, timezone
import time
from typing import Annotated, Any, Optional
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictProblem, NotFoundProblem, ValidationErrorProblem
from app.core.security import get_current_user
from app.domain.enums import FindingCategory, SeverityLevel, TriageStatus
from app.domain.schemas.analysis import (
    AdHocAnalysisRequest,
    AdHocAnalysisResponse,
    AdHocFinding,
    AnalysisEngineStatusResponse,
    AnalysisPipelineResultResponse,
    AnalysisPipelineRunRequest,
)
from app.domain.schemas.finding import FindingRead
from app.infrastructure.db.models import (
    BrandGuideline,
    BrandProfile,
    DocumentRevision,
    Finding,
    Submission,
    User,
    Workspace,
)
from app.infrastructure.db.session import get_async_session
from app.services.analysis.demo_fallback_cache import DemoFallbackCache
from app.services.analysis.deterministic_engine import DeterministicRuleEngine
from app.services.analysis.privacy_gate import PrivacyGateRouter
from app.services.analysis.temporal_fact_engine import TemporalFactEngine
from app.services.analysis.triage_orchestrator import TriageOrchestrator

router = APIRouter()
AuthenticatedUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/run",
    response_model=AnalysisPipelineResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute 4-Stage Intelligence Pipeline on Revision",
)
@router.post(
    "/",
    response_model=AnalysisPipelineResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute 4-Stage Intelligence Pipeline on Revision",
)
async def run_analysis_pipeline(
    payload: AnalysisPipelineRunRequest,
    current_user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AnalysisPipelineResultResponse:
    """
    Executes the 4-stage intelligence pipeline on an immutable document revision:
    1. Deterministic Rule Engine (O(N) Aho-Corasick, Readability, Passive Voice, Caps Abuse).
    2. Temporal Fact & Hybrid RAG Retrieval Engine (RRF, Staleness, Missing Evidence).
    3. Privacy Gate & Circuit-Breaker LLM Router (PII Scrubber, Cache).
    4. Calibrated Confidence Triage & 15% Stochastic Automation-Bias Safeguard.
    """
    # 1. Resolve Revision & Submission
    revision = await session.get(DocumentRevision, payload.revision_id)
    if not revision:
        raise NotFoundProblem(
            detail=f"DocumentRevision '{payload.revision_id}' not found.",
            resource_type="DocumentRevision",
            resource_id=str(payload.revision_id),
        )

    submission = await session.get(Submission, revision.submission_id)
    if not submission or submission.workspace_id != current_user.workspace_id:
        raise NotFoundProblem(
            detail=f"Submission for revision '{payload.revision_id}' not found in workspace.",
            resource_type="Submission",
            resource_id=str(revision.submission_id),
        )

    target_profile_id = payload.brand_profile_id or submission.brand_profile_id
    profile = await session.get(BrandProfile, target_profile_id) if target_profile_id else None
    if not profile or profile.workspace_id != current_user.workspace_id:
        fallback_stmt = (
            select(BrandProfile)
            .where(BrandProfile.workspace_id == current_user.workspace_id)
            .order_by(BrandProfile.created_at.asc())
        )
        fb_res = await session.execute(fallback_stmt)
        profile = fb_res.scalars().first()
        if not profile:
            raise NotFoundProblem(
                detail=f"Brand profile '{target_profile_id}' not found in workspace.",
                resource_type="BrandProfile",
                resource_id=str(target_profile_id),
            )

    # 2. Execute Pipeline
    kwargs = {
        "session": session,
        "revision_id": revision.id,
        "brand_profile_id": profile.id,
        "workspace_id": current_user.workspace_id,
        "content_text": revision.content_text,
        "requested_provider": payload.requested_provider,
        "preloaded_profile": profile,
    }
    if payload.audit_sample_rate is not None:
        kwargs["audit_sample_rate"] = payload.audit_sample_rate

    pipeline_result = await TriageOrchestrator.run_pipeline(**kwargs)

    # 3. Compile Response
    finding_reads = [FindingRead.model_validate(f) for f in pipeline_result.findings]

    return AnalysisPipelineResultResponse(
        revision_id=revision.id,
        submission_id=submission.id,
        total_findings=pipeline_result.total_findings,
        flagged_high_confidence=pipeline_result.flagged_high_confidence,
        routed_to_human_low_confidence=pipeline_result.routed_to_human_low_confidence,
        stale_facts_to_reverify=pipeline_result.stale_facts_to_reverify,
        needs_verification_missing_evidence=pipeline_result.needs_verification_missing_evidence,
        automation_bias_audits_injected=pipeline_result.automation_bias_audits_injected,
        processing_duration_ms=pipeline_result.processing_duration_ms,
        findings=finding_reads,
    )


@router.post(
    "/submissions/{submission_id}/run",
    response_model=AnalysisPipelineResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Pipeline on Latest Submission Head Revision",
)
async def run_analysis_for_submission(
    submission_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    requested_provider: str = Query(default="Azure OpenAI"),
) -> AnalysisPipelineResultResponse:
    """
    Convenience endpoint triggering compliance analysis on the active head revision of a submission.
    """
    submission = await session.get(Submission, submission_id)
    if not submission or submission.workspace_id != current_user.workspace_id:
        raise NotFoundProblem(
            detail=f"Submission '{submission_id}' not found in workspace.",
            resource_type="Submission",
            resource_id=str(submission_id),
        )

    if not submission.current_revision_id:
        raise ConflictProblem(
            detail=f"Submission '{submission_id}' has no committed head revision.",
            conflicting_field="current_revision_id",
        )

    run_payload = AnalysisPipelineRunRequest(
        revision_id=submission.current_revision_id,
        brand_profile_id=submission.brand_profile_id,
        requested_provider=requested_provider,
    )
    return await run_analysis_pipeline(
        payload=run_payload,
        current_user=current_user,
        session=session,
    )


@router.post(
    "/live",
    response_model=AdHocAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Real-Time Ad-Hoc Text Analysis for Live Editor",
)
async def analyze_live_text(
    payload: AdHocAnalysisRequest,
    current_user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AdHocAnalysisResponse:
    """
    Executes real-time, non-persisted compliance analysis on raw text.
    Powers the interactive document editor with instantaneous feedback:
    - Runs O(N) deterministic terminology & tone automata (<2ms).
    - Checks ground-truth approved facts for temporal staleness.
    - Evaluates privacy-gated tone checks without creating database revisions.
    """
    start_time = time.perf_counter()

    profile = await session.get(BrandProfile, payload.brand_profile_id) if payload.brand_profile_id else None
    if not profile or profile.workspace_id != current_user.workspace_id:
        fallback_stmt = (
            select(BrandProfile)
            .where(BrandProfile.workspace_id == current_user.workspace_id)
            .order_by(BrandProfile.created_at.asc())
        )
        fb_res = await session.execute(fallback_stmt)
        profile = fb_res.scalars().first()
        if not profile:
            raise NotFoundProblem(
                detail=f"Brand profile '{payload.brand_profile_id}' not found in workspace.",
                resource_type="BrandProfile",
                resource_id=str(payload.brand_profile_id),
            )

    # 0. Query active guidelines and workspace review rules to link findings to primary evidence sources
    ws = await session.get(Workspace, current_user.workspace_id)
    ws_rules = getattr(ws, "review_rules", {}) or {}
    conf_threshold = float(ws_rules.get("confidence_threshold", 0.85))

    guidelines_query = select(BrandGuideline).where(
        BrandGuideline.brand_profile_id == profile.id,
        BrandGuideline.is_active == True,  # noqa: E712
    )
    g_res = await session.execute(guidelines_query)
    guidelines = list(g_res.scalars().all())

    # 1. Deterministic Rule Hits
    deterministic_hits = DeterministicRuleEngine.analyze_document(
        content_text=payload.content_text,
        brand_profile=profile,
        guidelines=guidelines,
    )

    # 2. Temporal Fact Verification
    temporal_hits = await TemporalFactEngine.evaluate_claims(
        content_text=payload.content_text,
        workspace_id=current_user.workspace_id,
        session=session,
    )

    # 3. Privacy Gated Tone Analysis
    tone_hits = await PrivacyGateRouter.analyze_tone_and_messaging(
        content_text=payload.content_text,
        brand_profile=profile,
        workspace_id=current_user.workspace_id,
        session=session,
        requested_provider=payload.requested_provider,
    )

    findings: list[AdHocFinding] = []

    def _clean_suggestion(val: Any) -> Optional[str]:
        if isinstance(val, dict):
            return str(val.get("approved_term") or val.get("suggested_correction") or val.get("term") or val)
        if isinstance(val, list):
            return ", ".join(str(x) for x in val)
        return str(val) if val is not None else None

    for d in deterministic_hits:
        has_guideline = getattr(d, "linked_guideline_id", None) is not None
        status = TriageStatus.FLAGGED_HIGH_CONFIDENCE if has_guideline else TriageStatus.NEEDS_VERIFICATION
        ev_source = (
            getattr(d, "metadata", {}).get("rule_id")
            if getattr(d, "metadata", None)
            else f"Brand Guideline ({d.issue_category.value})"
        ) if has_guideline else "Unsubstantiated rule (Needs verification)"
        ev_link = f"/guidelines#{d.linked_guideline_id}" if has_guideline else None

        findings.append(
            AdHocFinding(
                issue_category=d.issue_category,
                severity=d.severity,
                confidence_score=1.0,
                triage_status=status,
                start_offset=d.start_offset,
                end_offset=d.end_offset,
                explanation_reason=d.explanation_reason,
                suggested_correction=_clean_suggestion(d.suggested_correction),
                detector_source=d.detector_source.value if hasattr(d.detector_source, "value") else str(d.detector_source),
                is_automation_bias_audit=False,
                linked_guideline_id=getattr(d, "linked_guideline_id", None),
                linked_fact_id=None,
                evidence_source=ev_source,
                evidence_link=ev_link,
            )
        )

    for t in temporal_hits:
        t_meta = getattr(t, "metadata", {}) or {}
        has_fact = getattr(t, "linked_fact_id", None) is not None
        status = t.triage_status
        if not has_fact or status == TriageStatus.NEEDS_VERIFICATION_MISSING_EVIDENCE:
            status = TriageStatus.NEEDS_VERIFICATION

        ev_source = t_meta.get("original_source_url") or t_meta.get("source_url") or ("Approved Corporate Fact" if has_fact else "Unverified assertion")
        ev_link = t_meta.get("original_source_url") or t_meta.get("source_url")

        findings.append(
            AdHocFinding(
                issue_category=t.issue_category,
                severity=t.severity,
                confidence_score=t.confidence_score,
                triage_status=status,
                start_offset=t.start_offset,
                end_offset=t.end_offset,
                explanation_reason=t.explanation_reason,
                suggested_correction=_clean_suggestion(t.suggested_correction),
                detector_source=t.detector_source.value if hasattr(t.detector_source, "value") else str(t.detector_source),
                is_automation_bias_audit=False,
                linked_guideline_id=None,
                linked_fact_id=getattr(t, "linked_fact_id", None),
                evidence_source=ev_source,
                evidence_link=ev_link,
            )
        )

    for tone in tone_hits:
        if tone.confidence_score >= 0.40:
            has_link = bool(getattr(tone, "linked_guideline_id", None) or getattr(tone, "linked_fact_id", None))
            if not has_link:
                status_val = TriageStatus.NEEDS_VERIFICATION
            elif tone.confidence_score >= conf_threshold:
                status_val = TriageStatus.FLAGGED_HIGH_CONFIDENCE
            else:
                status_val = TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE

            ev_source = f"Brand Voice Guideline ({profile.name})" if has_link else "Unverified Tone Pattern"
            ev_link = f"/guidelines#{tone.linked_guideline_id}" if getattr(tone, "linked_guideline_id", None) else ("/guidelines" if has_link else None)

            findings.append(
                AdHocFinding(
                    issue_category=tone.issue_category,
                    severity=tone.severity,
                    confidence_score=tone.confidence_score,
                    triage_status=status_val,
                    start_offset=tone.start_offset,
                    end_offset=tone.end_offset,
                    explanation_reason=tone.explanation_reason,
                    suggested_correction=tone.suggested_correction,
                    detector_source=tone.detector_source.value if hasattr(tone.detector_source, "value") else str(tone.detector_source),
                    is_automation_bias_audit=False,
                    linked_guideline_id=getattr(tone, "linked_guideline_id", None),
                    linked_fact_id=getattr(tone, "linked_fact_id", None),
                    evidence_source=ev_source,
                    evidence_link=ev_link,
                )
            )

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return AdHocAnalysisResponse(
        brand_profile_id=payload.brand_profile_id,
        total_findings=len(findings),
        processing_duration_ms=duration_ms,
        findings=findings,
    )


@router.get(
    "/revisions/{revision_id}/findings",
    response_model=list[FindingRead],
    status_code=status.HTTP_200_OK,
    summary="List Triaged Findings for Document Revision",
)
async def list_revision_findings(
    revision_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    triage_status: Optional[TriageStatus] = Query(default=None, description="Filter by triage status"),
    issue_category: Optional[FindingCategory] = Query(default=None, description="Filter by category"),
    severity: Optional[SeverityLevel] = Query(default=None, description="Filter by severity"),
) -> list[Finding]:
    """
    Retrieves all compliance findings detected on a specific document revision,
    sorted by character start offset for precise inline document highlighting.
    """
    revision = await session.get(DocumentRevision, revision_id)
    if not revision:
        raise NotFoundProblem(
            detail=f"DocumentRevision '{revision_id}' not found.",
            resource_type="DocumentRevision",
            resource_id=str(revision_id),
        )

    submission = await session.get(Submission, revision.submission_id)
    if not submission or submission.workspace_id != current_user.workspace_id:
        raise NotFoundProblem(
            detail=f"Submission for revision '{revision_id}' not found in workspace.",
            resource_type="Submission",
            resource_id=str(revision.submission_id),
        )

    query = (
        select(Finding)
        .where(Finding.revision_id == revision_id)
        .order_by(Finding.start_offset.asc())
    )
    if triage_status:
        query = query.where(Finding.triage_status == triage_status)
    if issue_category:
        query = query.where(Finding.issue_category == issue_category)
    if severity:
        query = query.where(Finding.severity == severity)

    result = await session.execute(query)
    return list(result.scalars().all())


@router.get(
    "/status",
    response_model=AnalysisEngineStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Intelligence Engine Operational Status",
)
async def get_analysis_engine_status(
    current_user: AuthenticatedUser,
) -> AnalysisEngineStatusResponse:
    """
    Inspects operational health of the analysis pipeline:
    - Circuit breaker state for external LLM inference.
    - Demo fallback cache pre-warmed entries count.
    - Supported privacy-gated inference providers.
    """
    cb_available = PrivacyGateRouter.circuit_breaker.is_available()
    cb_state = PrivacyGateRouter.circuit_breaker.state

    return AnalysisEngineStatusResponse(
        circuit_breaker_state=cb_state,
        circuit_breaker_available=cb_available,
        fallback_cache_size=DemoFallbackCache.get_cache_size(),
    )
