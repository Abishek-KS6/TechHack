"""
BrandShield AI - Immutable Revision Engine & Creator Suggestion Resolution.
Enforces append-only revision lineage when applying finding corrections:
- NEVER overwrites parent content.
- Generates vN+1 revision linked via parent_revision_id.
- Recalculates AST character offsets and visual coordinates.
- Computes unified diff patches against parent revision.
- Commits cryptographic audit records to audit_ledger.
"""

from datetime import datetime, timezone
import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictProblem, NotFoundProblem, ValidationErrorProblem
from app.domain.enums import AuditAction, CreatorAction, WorkflowState
from app.domain.schemas.submission import FindingResolutionRequest, FindingResolutionResponse
from app.domain.state_machine import SubmissionStateMachine
from app.infrastructure.db.models import DocumentRevision, Finding, Submission, User
from app.services.audit_service import AuditService
from app.services.ingestion.parser import OffsetPreservingASTParser
from app.services.workflow.diff_service import DiffService


class RevisionEngine:
    """
    Core engine managing append-only document revision DAG and finding resolution workflows.
    """

    @classmethod
    async def resolve_finding(
        cls,
        session: AsyncSession,
        submission_id: uuid.UUID,
        finding_id: uuid.UUID,
        actor: User,
        payload: FindingResolutionRequest,
    ) -> FindingResolutionResponse:
        """
        Executes author resolution (ACCEPT, REJECT, or EDIT) on a compliance finding:
        - If REJECT: Updates finding status and rationale without mutating document text.
        - If ACCEPT or EDIT: Computes new immutable DocumentRevision node (vN+1),
          recalculates character offsets and AST span map, generates diffs, and transitions state.
        """
        # 1. Resolve Submission and current active head revision
        submission = await session.get(Submission, submission_id)
        if not submission or submission.workspace_id != actor.workspace_id:
            raise NotFoundProblem(
                detail=f"Submission '{submission_id}' not found in workspace.",
                resource_type="Submission",
                resource_id=str(submission_id),
            )

        if payload.expected_version is not None:
            curr_ver = getattr(submission, "version_number", 1)
            if curr_ver != payload.expected_version:
                raise ConflictProblem(
                    detail=(
                        f"Optimistic Concurrency Conflict: Expected document version {payload.expected_version}, "
                        f"but active database version is {curr_ver}. Concurrent edit detected."
                    ),
                    conflicting_field="version_number",
                    conflicting_value=str(curr_ver),
                )

        if submission.workflow_state == WorkflowState.APPROVED:
            raise ConflictProblem(
                detail="Submission has already received final compliance approval. Content is locked from modification.",
                conflicting_field="workflow_state",
                conflicting_value="APPROVED",
            )

        if not submission.current_revision_id:
            raise ConflictProblem(
                detail=f"Submission '{submission_id}' has no active head revision.",
                conflicting_field="current_revision_id",
            )

        current_rev = await session.get(DocumentRevision, submission.current_revision_id)
        if not current_rev:
            raise NotFoundProblem(
                detail=f"Head revision '{submission.current_revision_id}' not found.",
                resource_type="DocumentRevision",
                resource_id=str(submission.current_revision_id),
            )

        # 2. Resolve Finding
        finding = await session.get(Finding, finding_id)
        if not finding:
            raise NotFoundProblem(
                detail=f"Finding '{finding_id}' not found.",
                resource_type="Finding",
                resource_id=str(finding_id),
            )

        # 3. Handle REJECT Action (No text mutation, state -> IN_CREATOR_REVISION)
        if payload.action == CreatorAction.REJECT:
            finding.creator_action = CreatorAction.REJECT
            finding.creator_comment = payload.comment
            finding.updated_at = datetime.now(timezone.utc)
            await session.flush()

            if submission.workflow_state in {WorkflowState.TRIAGED, WorkflowState.CHANGES_REQUESTED}:
                SubmissionStateMachine.transition(
                    submission=submission,
                    target_state=WorkflowState.IN_CREATOR_REVISION,
                    actor_role=actor.role,
                )
                await session.flush()

            await AuditService.record_event(
                session=session,
                action=AuditAction.FINDING_ACTION_UPDATED,
                workspace_id=submission.workspace_id,
                actor_id=actor.id,
                payload={
                    "submission_id": str(submission.id),
                    "finding_id": str(finding.id),
                    "action": CreatorAction.REJECT.value,
                    "comment": payload.comment,
                    "revision_id": str(current_rev.id),
                },
            )

            return FindingResolutionResponse(
                finding_id=finding.id,
                action=CreatorAction.REJECT,
                applied_correction=None,
                new_revision_id=None,
                new_revision_number=None,
                submission_id=submission.id,
                workflow_state=submission.workflow_state,
                comment=payload.comment,
            )

        # 4. Determine Replacement Text for ACCEPT or EDIT
        replacement: str
        if payload.action == CreatorAction.ACCEPT:
            if not finding.suggested_correction:
                raise ValidationErrorProblem(
                    detail="Finding does not contain a deterministic suggested correction to accept."
                )
            replacement = finding.suggested_correction
        elif payload.action == CreatorAction.EDIT:
            if not payload.edited_text:
                raise ValidationErrorProblem(
                    detail="'edited_text' must be provided when resolution action is 'EDIT'."
                )
            replacement = payload.edited_text
        else:
            raise ValidationErrorProblem(
                detail=f"Unsupported resolution action '{payload.action}'. Permitted: ACCEPT, REJECT, EDIT."
            )

        # 5. Apply correction into parent content: NEVER overwrite original snapshot!
        parent_text = current_rev.content_text
        s_start = max(0, min(finding.start_offset, len(parent_text)))
        s_end = max(s_start, min(finding.end_offset, len(parent_text)))

        new_content = parent_text[:s_start] + replacement + parent_text[s_end:]

        # 6. Recalculate character offsets and AST span map
        parsed_doc = OffsetPreservingASTParser.parse_text(new_content)
        new_span_map = parsed_doc.ast_span_map

        # 7. Compute unified line diff against parent revision
        diff_summary = DiffService.compute_line_diff(current_rev.content_text, new_content)
        new_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()

        # 8. Commit append-only child DocumentRevision (vN+1)
        new_revision = DocumentRevision(
            id=uuid.uuid4(),
            submission_id=submission.id,
            revision_number=current_rev.revision_number + 1,
            parent_revision_id=current_rev.id,
            content_text=new_content,
            ast_span_map=new_span_map,
            created_by_id=actor.id,
            sha256_content_hash=new_hash,
            diff_summary=diff_summary,
            created_at=datetime.now(timezone.utc),
        )
        session.add(new_revision)
        await session.flush()

        # Update submission head pointer, version counter, and lifecycle state
        submission.current_revision_id = new_revision.id
        if hasattr(submission, "version_number"):
            submission.version_number = (submission.version_number or 1) + 1
        if submission.workflow_state in {WorkflowState.TRIAGED, WorkflowState.CHANGES_REQUESTED}:
            SubmissionStateMachine.transition(
                submission=submission,
                target_state=WorkflowState.IN_CREATOR_REVISION,
                actor_role=actor.role,
            )
        await session.flush()

        # Update finding resolution status
        finding.creator_action = payload.action
        finding.creator_comment = payload.comment
        finding.updated_at = datetime.now(timezone.utc)
        await session.flush()

        # 9. Commit audit events
        await AuditService.record_event(
            session=session,
            action=AuditAction.FINDING_ACTION_UPDATED,
            workspace_id=submission.workspace_id,
            actor_id=actor.id,
            payload={
                "submission_id": str(submission.id),
                "finding_id": str(finding.id),
                "action": payload.action.value,
                "applied_text": replacement,
                "parent_revision_id": str(current_rev.id),
                "new_revision_id": str(new_revision.id),
            },
        )

        await AuditService.record_event(
            session=session,
            action=AuditAction.REVISION_COMMITTED,
            workspace_id=submission.workspace_id,
            actor_id=actor.id,
            payload={
                "submission_id": str(submission.id),
                "revision_number": new_revision.revision_number,
                "revision_id": str(new_revision.id),
                "parent_revision_id": str(current_rev.id),
                "sha256_hash": new_hash,
                "triggered_by_finding_id": str(finding.id),
                "diff_summary": diff_summary,
            },
        )

        return FindingResolutionResponse(
            finding_id=finding.id,
            action=payload.action,
            applied_correction=replacement,
            new_revision_id=new_revision.id,
            new_revision_number=new_revision.revision_number,
            submission_id=submission.id,
            workflow_state=submission.workflow_state,
            comment=payload.comment,
        )

    @classmethod
    async def submit_for_human_review(
        cls,
        session: AsyncSession,
        submission_id: uuid.UUID,
        actor: User,
    ) -> Submission:
        """
        Transitions a revised submission into IN_HUMAN_REVIEW status.
        Requires creator role and enforces FSM transition legality.
        """
        submission = await session.get(Submission, submission_id)
        if not submission or submission.workspace_id != actor.workspace_id:
            raise NotFoundProblem(
                detail=f"Submission '{submission_id}' not found in workspace.",
                resource_type="Submission",
                resource_id=str(submission_id),
            )

        SubmissionStateMachine.transition(
            submission=submission,
            target_state=WorkflowState.IN_HUMAN_REVIEW,
            actor_role=actor.role,
        )
        submission.updated_at = datetime.now(timezone.utc)
        await session.flush()

        await AuditService.record_event(
            session=session,
            action=AuditAction.DOCUMENT_SUBMITTED,
            workspace_id=submission.workspace_id,
            actor_id=actor.id,
            payload={
                "submission_id": str(submission.id),
                "workflow_state": WorkflowState.IN_HUMAN_REVIEW.value,
                "revision_id": str(submission.current_revision_id),
            },
        )
        return submission
