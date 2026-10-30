"""
BrandShield AI - Git-Like Immutable Document Revision DAG Service
Guarantees append-only content immutability, SHA-256 verification, and workflow state transitions.
"""

from datetime import datetime, timezone
import difflib
import hashlib
from typing import Any, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import AuditAction, ReviewSignOff, WorkflowState
from app.domain.schemas.submission import ReviewDecisionCreate, SubmissionCreate
from app.infrastructure.db.models import DocumentRevision, ReviewDecision, Submission
from app.services.audit_service import AuditService


class SubmissionService:
    """
    Core Domain Service managing the Git-like document revision DAG and workflow transitions.
    """

    @staticmethod
    def calculate_sha256(content: str) -> str:
        """Computes SHA-256 checksum of document content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_diff(old_text: str, new_text: str) -> dict[str, Any]:
        """Generates unified line-level diff summary between revisions."""
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        diff = list(difflib.unified_diff(old_lines, new_lines, fromfile="parent", tofile="child"))
        return {
            "diff_lines": diff,
            "lines_added": sum(1 for line in diff if line.startswith("+") and not line.startswith("+++")),
            "lines_removed": sum(1 for line in diff if line.startswith("-") and not line.startswith("---")),
        }

    @classmethod
    async def create_submission(
        cls,
        session: AsyncSession,
        payload: SubmissionCreate,
        creator_id: uuid.UUID,
    ) -> Submission:
        """
        Creates a root submission and its initial Genesis revision (v1).
        """
        content_hash = cls.calculate_sha256(payload.initial_content)

        submission = Submission(
            workspace_id=payload.workspace_id,
            brand_profile_id=payload.brand_profile_id,
            creator_id=creator_id,
            title=payload.title,
            document_type=payload.document_type,
            workflow_state=WorkflowState.SUBMITTED,
        )
        session.add(submission)
        await session.flush()

        genesis_revision = DocumentRevision(
            submission_id=submission.id,
            revision_number=1,
            parent_revision_id=None,
            content_text=payload.initial_content,
            ast_span_map=payload.ast_span_map,
            created_by_id=creator_id,
            sha256_content_hash=content_hash,
            diff_summary=None,
        )
        session.add(genesis_revision)
        await session.flush()

        submission.current_revision_id = genesis_revision.id
        await session.flush()

        await AuditService.record_event(
            session=session,
            action=AuditAction.DOCUMENT_SUBMITTED,
            workspace_id=payload.workspace_id,
            actor_id=creator_id,
            payload={
                "submission_id": str(submission.id),
                "revision_id": str(genesis_revision.id),
                "title": submission.title,
                "sha256_hash": content_hash,
                "document_type": submission.document_type,
            },
        )
        return submission

    @classmethod
    async def commit_revision(
        cls,
        session: AsyncSession,
        submission_id: uuid.UUID,
        new_content: str,
        ast_span_map: list[dict[str, Any]],
        creator_id: uuid.UUID,
    ) -> DocumentRevision:
        """
        Appends an immutable child revision to the submission DAG (vN+1).
        NEVER overwrites the parent; links explicitly via parent_revision_id.
        """
        query = (
            select(Submission)
            .where(Submission.id == submission_id)
            .options(selectinload(Submission.current_revision))
        )
        result = await session.execute(query)
        submission = result.scalar_one_or_none()

        if not submission:
            raise ValueError(f"Submission {submission_id} does not exist.")

        parent_rev = submission.current_revision
        if not parent_rev:
            raise ValueError(f"Submission {submission_id} has no valid head revision.")

        parent_plain = parent_rev.get_decrypted_content() if hasattr(parent_rev, "get_decrypted_content") else parent_rev.content_text
        new_hash = cls.calculate_sha256(new_content)
        diff_summary = cls.compute_diff(parent_plain, new_content)

        new_revision = DocumentRevision(
            submission_id=submission.id,
            revision_number=parent_rev.revision_number + 1,
            parent_revision_id=parent_rev.id,
            content_text=new_content,
            ast_span_map=ast_span_map,
            created_by_id=creator_id,
            sha256_content_hash=new_hash,
            diff_summary=diff_summary,
        )
        session.add(new_revision)
        await session.flush()

        submission.current_revision_id = new_revision.id
        submission.workflow_state = WorkflowState.ANALYZING
        await session.flush()

        await AuditService.record_event(
            session=session,
            action=AuditAction.REVISION_COMMITTED,
            workspace_id=submission.workspace_id,
            actor_id=creator_id,
            payload={
                "submission_id": str(submission.id),
                "revision_number": new_revision.revision_number,
                "revision_id": str(new_revision.id),
                "parent_revision_id": str(parent_rev.id),
                "sha256_hash": new_hash,
                "diff_summary": diff_summary,
            },
        )
        return new_revision

    @classmethod
    async def record_review_decision(
        cls,
        session: AsyncSession,
        submission_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        payload: ReviewDecisionCreate,
    ) -> ReviewDecision:
        """
        Records human compliance reviewer sign-off and transitions workflow state.
        """
        submission = await session.get(Submission, submission_id)
        if not submission:
            raise ValueError(f"Submission {submission_id} does not exist.")

        if not submission.current_revision_id:
            raise ValueError("Cannot review a submission with no current revision.")

        decision = ReviewDecision(
            submission_id=submission_id,
            revision_id=submission.current_revision_id,
            reviewer_id=reviewer_id,
            decision=payload.decision,
            comments=payload.comments,
            stipulations=payload.stipulations,
        )
        session.add(decision)

        # Transition state
        if payload.decision == ReviewSignOff.APPROVED:
            submission.workflow_state = WorkflowState.APPROVED
        else:
            submission.workflow_state = WorkflowState.CHANGES_REQUESTED

        await session.flush()

        await AuditService.record_event(
            session=session,
            action=AuditAction.REVIEW_DECIDED,
            workspace_id=submission.workspace_id,
            actor_id=reviewer_id,
            payload={
                "submission_id": str(submission.id),
                "revision_id": str(submission.current_revision_id),
                "decision": payload.decision.value,
                "comments": payload.comments,
            },
        )
        return decision
