"""
BrandShield AI - Document Submissions, Ingestion & AST Tokenization Router.
Exposes multipart file upload and raw text ingestion endpoints:
- Verifies MIME magic signatures (PDF %PDF-, DOCX PK\\x03\\x04).
- Defends against VBA macros, executable payload streams, and XML/zip bombs.
- Performs offset-preserving AST tokenization (character offsets, bounding boxes, styles).
- Creates Submission and Genesis Revision (v1) storing raw text, ast_span_map, and sha256_content_hash.
- Cryptographically seals submission in the audit_ledger.
- Supports revision commits and reviewer sign-off decisions in the DAG.
"""

from datetime import datetime, timezone
import hashlib
from typing import Annotated, Any, Optional
import json
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictProblem, NotFoundProblem, ValidationErrorProblem
from app.core.security import RequireRole, get_current_user
from app.domain.enums import AuditAction, UserRole, WorkflowState
from app.domain.schemas.submission import (
    DocumentRevisionCreate,
    DocumentRevisionRead,
    ReviewDecisionCreate,
    ReviewDecisionRead,
    SubmissionCreate,
    SubmissionRead,
    TextSubmissionCreate,
)
from app.infrastructure.db.models import (
    BrandProfile,
    DocumentRevision,
    ReviewDecision,
    Submission,
    User,
)
from app.infrastructure.db.session import get_async_session
from app.services.analysis.triage_orchestrator import TriageOrchestrator
from app.services.audit_service import AuditService
from app.services.ingestion.parser import (
    OffsetPreservingASTParser,
    ParsedDocument,
    compute_sha256_async,
    parse_docx_async,
    parse_pdf_async,
    parse_text_async,
)
from app.services.ingestion.validator import UploadValidator
from app.services.submission_service import SubmissionService

router = APIRouter()

AuthorizedCreator = Annotated[User, Depends(RequireRole(UserRole.CREATOR, UserRole.ADMINISTRATOR))]
AuthorizedReviewer = Annotated[User, Depends(RequireRole(UserRole.REVIEWER, UserRole.ADMINISTRATOR))]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]


@router.post("/text", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
async def submit_text_document(
    payload: TextSubmissionCreate,
    creator: AuthorizedCreator,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Submission:
    """
    Ingests raw text or Markdown, normalizes Unicode (NFC), parses offset-preserving
    AST span map, establishes Genesis revision #1 (v1), and commits event to audit ledger.
    """
    profile = await session.get(BrandProfile, payload.brand_profile_id)
    if not profile or profile.workspace_id != creator.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{payload.brand_profile_id}' not found in workspace.",
            resource_type="BrandProfile",
            resource_id=str(payload.brand_profile_id),
        )

    doc_type = payload.document_type.upper()
    if doc_type not in ("TEXT", "MARKDOWN"):
        doc_type = "TEXT"

    parsed: ParsedDocument = OffsetPreservingASTParser.parse_text(
        raw_input=payload.content,
        document_type=doc_type,
    )

    return await _create_submission_and_genesis_revision(
        session=session,
        creator=creator,
        brand_profile_id=payload.brand_profile_id,
        title=payload.title,
        document_type=doc_type,
        parsed=parsed,
    )


@router.post("/upload", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
async def upload_document_asset(
    creator: AuthorizedCreator,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    title: str = Form(..., min_length=2, max_length=255),
    brand_profile_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
) -> Submission:
    """
    Uploads and verifies document binary assets (PDF, DOCX, TXT, MD):
    1. Enforces magic byte verification (rejects spoofed extensions).
    2. Scans for active VBA macros, executable streams, and XML/zip bombs.
    3. Tokenizes document into offset-preserved AST nodes (bboxes for PDF, styles for DOCX).
    4. Commits Submission and Genesis Revision (v1) with SHA-256 integrity hash.
    5. Appends cryptographic audit entry to audit_ledger.
    """
    profile = await session.get(BrandProfile, brand_profile_id)
    if not profile or profile.workspace_id != creator.workspace_id:
        raise NotFoundProblem(
            detail=f"Brand profile '{brand_profile_id}' not found in workspace.",
            resource_type="BrandProfile",
            resource_id=str(brand_profile_id),
        )

    # Streaming chunk validation (64KB loop with max-size abort in flight)
    file_bytes, validated = await UploadValidator.validate_upload_stream(file)

    # Route to non-blocking specialized AST parser (guarded by Semaphore(8))
    if validated.document_type == "PDF":
        parsed = await parse_pdf_async(file_bytes)
    elif validated.document_type == "DOCX":
        parsed = await parse_docx_async(file_bytes)
    elif validated.document_type in ("TEXT", "MARKDOWN"):
        parsed = await parse_text_async(
            raw_input=file_bytes.decode("utf-8"),
            document_type=validated.document_type,
        )
    else:
        raise ValidationErrorProblem(
            detail=f"Unsupported document type: {validated.document_type}"
        )

    return await _create_submission_and_genesis_revision(
        session=session,
        creator=creator,
        brand_profile_id=brand_profile_id,
        title=title,
        document_type=validated.document_type,
        parsed=parsed,
        source_filename=validated.clean_filename,
    )


@router.post("/", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
async def create_raw_submission(
    payload: SubmissionCreate,
    creator: AuthorizedCreator,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Submission:
    """Creates a submission from structured payload establishes Genesis revision (v1)."""
    return await SubmissionService.create_submission(
        session=session,
        payload=payload,
        creator_id=creator.id,
    )


async def _create_submission_and_genesis_revision(
    session: AsyncSession,
    creator: User,
    brand_profile_id: uuid.UUID,
    title: str,
    document_type: str,
    parsed: ParsedDocument,
    source_filename: Optional[str] = None,
) -> Submission:
    """
    Atomic helper to create Submission, DocumentRevision #1 (v1), and cryptographic audit entry.
    """
    sha256_hash = await compute_sha256_async(parsed.raw_text.encode("utf-8"))

    now = datetime.now(timezone.utc)
    sub_id = uuid.uuid4()
    rev_id = uuid.uuid4()

    submission = Submission(
        id=sub_id,
        workspace_id=creator.workspace_id,
        brand_profile_id=brand_profile_id,
        creator_id=creator.id,
        title=title,
        document_type=document_type,
        workflow_state=WorkflowState.SUBMITTED,
        created_at=now,
        updated_at=now,
    )
    session.add(submission)
    await session.flush()

    genesis_revision = DocumentRevision(
        id=rev_id,
        submission_id=submission.id,
        revision_number=1,
        parent_revision_id=None,
        content_text=parsed.raw_text,
        ast_span_map=parsed.ast_span_map,
        created_by_id=creator.id,
        sha256_content_hash=sha256_hash,
        diff_summary=None,
        created_at=now,
    )
    session.add(genesis_revision)
    await session.flush()

    # Link submission tip pointer
    submission.current_revision_id = genesis_revision.id
    await session.flush()

    # Commit event to cryptographic audit ledger
    await AuditService.record_event(
        session=session,
        action=AuditAction.DOCUMENT_SUBMITTED,
        workspace_id=creator.workspace_id,
        actor_id=creator.id,
        payload={
            "submission_id": str(submission.id),
            "revision_id": str(genesis_revision.id),
            "revision_number": 1,
            "title": submission.title,
            "document_type": document_type,
            "sha256_content_hash": sha256_hash,
            "total_spans": parsed.total_spans,
            "total_characters": parsed.total_characters,
            "total_words": parsed.total_words,
            "source_filename": source_filename,
        },
    )
    await session.commit()
    await session.refresh(submission)
    return submission


@router.get("/", response_model=list[SubmissionRead])
async def list_workspace_submissions(
    current_user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    workflow_state: Optional[WorkflowState] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Submission]:
    """Lists submissions in authenticated user's workspace."""
    query = (
        select(Submission)
        .where(Submission.workspace_id == current_user.workspace_id)
        .order_by(Submission.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    # Role-based submission visibility enforcement
    if current_user.role == UserRole.CREATOR:
        query = query.where(Submission.creator_id == current_user.id)
    elif current_user.role == UserRole.REVIEWER and not workflow_state:
        # Reviewer sees all submissions in review or past review
        query = query.where(Submission.workflow_state.in_([
            WorkflowState.IN_HUMAN_REVIEW,
            WorkflowState.TRIAGED,
            WorkflowState.APPROVED,
            WorkflowState.CHANGES_REQUESTED,
        ]))
    if workflow_state:
        query = query.where(Submission.workflow_state == workflow_state)

    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    current_user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, Any]:
    """Computes real persisted dashboard metrics for current user workspace."""
    from sqlalchemy import func
    from app.infrastructure.db.models import Finding

    sub_query = select(Submission.workflow_state, func.count(Submission.id)).where(
        Submission.workspace_id == current_user.workspace_id
    )
    if current_user.role == UserRole.CREATOR:
        sub_query = sub_query.where(Submission.creator_id == current_user.id)
    sub_query = sub_query.group_by(Submission.workflow_state)

    sub_res = await session.execute(sub_query)
    state_counts = {str(state.value if hasattr(state, "value") else state): count for state, count in sub_res.all()}

    total_submissions = sum(state_counts.values())
    awaiting_review = state_counts.get(WorkflowState.IN_HUMAN_REVIEW.value, 0) + state_counts.get(WorkflowState.TRIAGED.value, 0)
    approved = state_counts.get(WorkflowState.APPROVED.value, 0)
    changes_requested = state_counts.get(WorkflowState.CHANGES_REQUESTED.value, 0)

    finding_query = (
        select(Finding.issue_category, Finding.severity, func.count(Finding.id))
        .join(DocumentRevision, Finding.revision_id == DocumentRevision.id)
        .join(Submission, DocumentRevision.submission_id == Submission.id)
        .where(Submission.workspace_id == current_user.workspace_id)
    )
    if current_user.role == UserRole.CREATOR:
        finding_query = finding_query.where(Submission.creator_id == current_user.id)
    finding_query = finding_query.group_by(Finding.issue_category, Finding.severity)
    f_res = await session.execute(finding_query)
    findings_by_category: dict[str, int] = {}
    findings_by_severity: dict[str, int] = {}
    total_findings = 0
    for cat, sev, cnt in f_res.all():
        cat_key = str(cat.value if hasattr(cat, "value") else cat)
        sev_key = str(sev.value if hasattr(sev, "value") else sev)
        findings_by_category[cat_key] = findings_by_category.get(cat_key, 0) + cnt
        findings_by_severity[sev_key] = findings_by_severity.get(sev_key, 0) + cnt
        total_findings += cnt

    return {
        "total_submissions": total_submissions,
        "awaiting_review": awaiting_review,
        "approved": approved,
        "changes_requested": changes_requested,
        "state_distribution": state_counts,
        "total_findings": total_findings,
        "findings_by_category": findings_by_category,
        "findings_by_severity": findings_by_severity,
    }


@router.get("/{submission_id}", response_model=SubmissionRead)
async def get_submission(
    submission_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Submission:
    """Retrieves single submission by unique ID."""
    submission = await session.get(Submission, submission_id)
    if not submission or submission.workspace_id != current_user.workspace_id:
        raise NotFoundProblem(
            detail=f"Submission '{submission_id}' not found in workspace.",
            resource_type="Submission",
            resource_id=str(submission_id),
        )
    return submission


@router.get("/{submission_id}/revisions", response_model=list[DocumentRevisionRead])
async def list_submission_revisions(
    submission_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[DocumentRevision]:
    """Retrieves full immutable revision history DAG for a submission."""
    submission = await session.get(Submission, submission_id)
    if not submission or submission.workspace_id != current_user.workspace_id:
        raise NotFoundProblem(
            detail=f"Submission '{submission_id}' not found in workspace.",
            resource_type="Submission",
            resource_id=str(submission_id),
        )

    query = (
        select(DocumentRevision)
        .where(DocumentRevision.submission_id == submission_id)
        .order_by(DocumentRevision.revision_number.asc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/{submission_id}/revisions/{revision_number}", response_model=DocumentRevisionRead)
async def get_submission_revision(
    submission_id: uuid.UUID,
    revision_number: int,
    current_user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> DocumentRevision:
    """Retrieves specific revision node including complete AST span map."""
    submission = await session.get(Submission, submission_id)
    if not submission or submission.workspace_id != current_user.workspace_id:
        raise NotFoundProblem(
            detail=f"Submission '{submission_id}' not found in workspace.",
            resource_type="Submission",
            resource_id=str(submission_id),
        )

    query = select(DocumentRevision).where(
        DocumentRevision.submission_id == submission_id,
        DocumentRevision.revision_number == revision_number,
    )
    result = await session.execute(query)
    revision = result.scalar_one_or_none()
    if not revision:
        raise NotFoundProblem(
            detail=f"Revision #{revision_number} not found for submission '{submission_id}'.",
            resource_type="DocumentRevision",
            resource_id=str(revision_number),
        )
    return revision


@router.post(
    "/{submission_id}/revisions",
    response_model=DocumentRevisionRead,
    status_code=status.HTTP_201_CREATED,
)
async def commit_revision(
    submission_id: uuid.UUID,
    payload: DocumentRevisionCreate,
    creator: AuthorizedCreator,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> DocumentRevision:
    """Appends an immutable revision node to the submission DAG with diff computation."""
    return await SubmissionService.commit_revision(
        session=session,
        submission_id=submission_id,
        new_content=payload.content_text,
        ast_span_map=payload.ast_span_map,
        creator_id=creator.id,
    )


@router.post(
    "/{submission_id}/decisions",
    response_model=ReviewDecisionRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_review_decision(
    submission_id: uuid.UUID,
    payload: ReviewDecisionCreate,
    reviewer: AuthorizedReviewer,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ReviewDecision:
    """Records human compliance review sign-off (APPROVED or CHANGES_REQUESTED)."""
    return await SubmissionService.record_review_decision(
        session=session,
        submission_id=submission_id,
        reviewer_id=reviewer.id,
        payload=payload,
    )


@router.get(
    "/{submission_id}/analyze/stream",
    summary="Real-time SSE Streaming of 4-Stage Intelligence Pipeline",
    response_class=StreamingResponse,
)
async def stream_submission_analysis(
    submission_id: uuid.UUID,
    user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    requested_provider: str = Query(default="Azure OpenAI"),
) -> StreamingResponse:
    """
    Streams Server-Sent Events (SSE) representing real-time pipeline execution stages
    with millisecond latencies to the React frontend dashboard:
    - STAGE_1_DETERMINISTIC_COMPLETE
    - STAGE_2_TEMPORAL_FACT_RAG_COMPLETE
    - STAGE_3_PRIVACY_GATE_VERIFIED
    - STAGE_4_TRIAGE_COMPLETE
    - PIPELINE_COMPLETE
    """
    submission = await session.get(Submission, submission_id)
    if not submission or submission.workspace_id != user.workspace_id:
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

    revision = await session.get(DocumentRevision, submission.current_revision_id)
    if not revision:
        raise NotFoundProblem(
            detail=f"Head revision '{submission.current_revision_id}' not found.",
            resource_type="DocumentRevision",
            resource_id=str(submission.current_revision_id),
        )

    async def event_generator():
        try:
            async for item in TriageOrchestrator.stream_pipeline(
                session=session,
                revision_id=revision.id,
                brand_profile_id=submission.brand_profile_id,
                workspace_id=user.workspace_id,
                content_text=revision.content_text,
                requested_provider=requested_provider,
            ):
                event_name = item["event"]
                event_data = json.dumps(item["data"])
                yield f"event: {event_name}\ndata: {event_data}\n\n"
        except Exception as exc:
            err_data = json.dumps({"error": str(exc), "stage": "PIPELINE_ERROR"})
            yield f"event: PIPELINE_ERROR\ndata: {err_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
