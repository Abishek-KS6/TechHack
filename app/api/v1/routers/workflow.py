"""
BrandShield AI - Human Review Workflow & Revision Engine API Router.
Exposes endpoints for:
1. Creator suggestion resolution (POST /submissions/{id}/findings/{finding_id}/resolve).
2. Creator submit for review (POST /submissions/{id}/submit-for-review).
3. Human reviewer sign-off (POST /submissions/{id}/review).
4. Full revision lineage & side-by-side token diffs (GET /submissions/{id}/revisions/diff).
"""

from typing import Annotated, Any, Optional
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import RequireRole, get_current_user
from app.domain.enums import UserRole
from app.domain.schemas.submission import (
    FindingResolutionRequest,
    FindingResolutionResponse,
    ReviewDecisionRead,
    ReviewSubmissionRequest,
    RevisionDiffResponse,
    SubmissionRead,
)
from app.infrastructure.db.models import ReviewDecision, Submission, User
from app.infrastructure.db.session import get_async_session
from app.services.workflow.diff_service import DiffService
from app.services.workflow.review_service import WorkflowReviewService
from app.services.workflow.revision_engine import RevisionEngine

router = APIRouter()

AuthorizedCreator = Annotated[User, Depends(RequireRole(UserRole.CREATOR, UserRole.ADMINISTRATOR))]
AuthorizedReviewer = Annotated[User, Depends(RequireRole(UserRole.REVIEWER, UserRole.ADMINISTRATOR))]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/{submission_id}/findings/{finding_id}/resolve",
    response_model=FindingResolutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Creator Suggestion Resolution",
)
async def resolve_finding_suggestion(
    submission_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: FindingResolutionRequest,
    creator: AuthorizedCreator,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> FindingResolutionResponse:
    """
    Allows the Creator to ACCEPT, REJECT, or EDIT a finding correction:
    - Never overwrites the original submission snapshot.
    - If accepted or edited: computes a new immutable DocumentRevision node (vN+1),
      recalculates character offsets and AST span map, computes unified diff,
      and transitions submission to IN_CREATOR_REVISION.
    - Emits immutable records to the audit ledger.
    """
    return await RevisionEngine.resolve_finding(
        session=session,
        submission_id=submission_id,
        finding_id=finding_id,
        actor=creator,
        payload=payload,
    )


@router.post(
    "/{submission_id}/submit-for-review",
    response_model=SubmissionRead,
    status_code=status.HTTP_200_OK,
    summary="Submit Revised Content for Human Compliance Review",
)
async def submit_content_for_review(
    submission_id: uuid.UUID,
    creator: AuthorizedCreator,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Submission:
    """
    Transitions submission from IN_CREATOR_REVISION to IN_HUMAN_REVIEW.
    Ensures legal state transition via the strict finite state machine.
    """
    return await RevisionEngine.submit_for_human_review(
        session=session,
        submission_id=submission_id,
        actor=creator,
    )


@router.post(
    "/{submission_id}/review",
    response_model=ReviewDecisionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Human Reviewer Governance Sign-Off",
)
async def execute_human_review(
    submission_id: uuid.UUID,
    payload: ReviewSubmissionRequest,
    reviewer: AuthorizedReviewer,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ReviewDecision:
    """
    Executes certified human compliance reviewer determination (APPROVED or CHANGES_REQUESTED):
    - Guarantees AI cannot approve: requires authenticated REVIEWER or ADMINISTRATOR role.
    - Anti-Rubber-Stamping: Requires explicit verification for findings flagged by the
      Automation-Bias Safeguard (is_automation_bias_audit=True) before approval can be granted.
    - Records inline comments and conditional approval stipulations.
    - Cryptographically logs REVIEW_DECIDED in the audit ledger.
    """
    return await WorkflowReviewService.execute_review_decision(
        session=session,
        submission_id=submission_id,
        reviewer=reviewer,
        payload=payload,
    )


@router.post(
    "/{submission_id}/assign-reviewer",
    status_code=status.HTTP_200_OK,
    summary="Assign Reviewer to Submission",
)
async def assign_submission_reviewer(
    submission_id: uuid.UUID,
    reviewer: AuthorizedReviewer,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    target_reviewer_id: Optional[uuid.UUID] = None,
) -> dict[str, Any]:
    """Assigns an authorized reviewer or allows an administrator to act as assigned reviewer."""
    submission = await session.get(Submission, submission_id)
    if not submission or submission.workspace_id != reviewer.workspace_id:
        raise NotFoundProblem(
            detail=f"Submission '{submission_id}' not found in workspace.",
            resource_type="Submission",
            resource_id=str(submission_id),
        )
    assigned_id = target_reviewer_id or reviewer.id
    submission.assigned_reviewer_id = assigned_id
    await session.commit()
    return {"status": "assigned", "assigned_reviewer_id": str(assigned_id)}


@router.get(
    "/{submission_id}/revisions/diff",
    response_model=RevisionDiffResponse,
    status_code=status.HTTP_200_OK,
    summary="Revision Lineage & Side-by-Side Token Diff",
)
async def get_revision_lineage_and_diff(
    submission_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    from_revision: int = Query(default=1, ge=1, description="Base revision number for comparison"),
    to_revision: Optional[int] = Query(default=None, ge=1, description="Target revision number (defaults to latest)"),
) -> RevisionDiffResponse:
    """
    Returns the complete append-only revision DAG lineage and exact side-by-side
    token diffs and unified line diffs from base revision to latest revision.
    """
    return await DiffService.get_revision_diff(
        session=session,
        submission_id=submission_id,
        from_revision=from_revision,
        to_revision=to_revision,
    )


@router.get(
    "/{submission_id}/reviews",
    response_model=list[ReviewDecisionRead],
    status_code=status.HTTP_200_OK,
    summary="List Review Decisions for Submission",
)
async def list_submission_reviews(
    submission_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[ReviewDecision]:
    """Retrieves all human review decisions, comments, and reviewer determinations for a submission."""
    submission = await session.get(Submission, submission_id)
    if not submission or submission.workspace_id != current_user.workspace_id:
        raise NotFoundProblem(
            detail=f"Submission '{submission_id}' not found in workspace.",
            resource_type="Submission",
            resource_id=str(submission_id),
        )
    query = (
        select(ReviewDecision)
        .where(ReviewDecision.submission_id == submission_id)
        .order_by(ReviewDecision.decided_at.desc())
    )
    result = await session.execute(query)
    return list(result.scalars().all())
