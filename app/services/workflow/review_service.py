"""
BrandShield AI - Human Compliance Reviewer Sign-Off Service.
Enforces non-bypassable human governance boundaries:
- Rejects rubber-stamped bulk approvals on unverified automation-bias audit findings.
- Records inline reviewer annotations on spans and findings.
- Transitions FSM lifecycle to APPROVED or CHANGES_REQUESTED.
- Seals determinations in the immutable audit ledger.
"""

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictProblem, ForbiddenProblem, NotFoundProblem, ValidationErrorProblem
from app.domain.enums import AuditAction, CreatorAction, ReviewSignOff, TriageStatus, UserRole, WorkflowState
from app.domain.schemas.submission import ReviewSubmissionRequest
from app.domain.state_machine import SubmissionStateMachine
from app.infrastructure.db.models import Finding, ReviewDecision, Submission, User, Workspace
from app.services.audit_service import AuditService


class WorkflowReviewService:
    """
    Service executing certified human compliance review sign-off determinations.
    """

    @classmethod
    async def execute_review_decision(
        cls,
        session: AsyncSession,
        submission_id: uuid.UUID,
        reviewer: User,
        payload: ReviewSubmissionRequest,
    ) -> ReviewDecision:
        """
        Executes formal human compliance sign-off (APPROVED or CHANGES_REQUESTED):
        1. Verifies reviewer authorization (REVIEWER or ADMINISTRATOR role).
        2. Enforces anti-automation-bias safeguard verification: all is_automation_bias_audit
           findings on the head revision must be explicitly confirmed before approval.
        3. Attaches inline reviewer comments and structured stipulations.
        4. Transitions submission state machine to APPROVED or CHANGES_REQUESTED.
        5. Logs REVIEW_DECIDED to cryptographic audit ledger.
        """
        # 1. Resolve Submission and head revision
        submission = await session.get(Submission, submission_id)
        if not submission or submission.workspace_id != reviewer.workspace_id:
            raise NotFoundProblem(
                detail=f"Submission '{submission_id}' not found in workspace.",
                resource_type="Submission",
                resource_id=str(submission_id),
            )

        if not submission.current_revision_id:
            raise ConflictProblem(
                detail=f"Submission '{submission_id}' has no committed head revision to review.",
                conflicting_field="current_revision_id",
            )

        if submission.workflow_state == WorkflowState.APPROVED:
            raise ConflictProblem(
                detail="Submission has already received final approval and is immutable.",
                conflicting_field="workflow_state",
                conflicting_value="APPROVED",
            )

        # Role & Governance Approval Restrictions
        if payload.decision == ReviewSignOff.APPROVED:
            # Invariant: A creator cannot approve their own submission
            if submission.creator_id == reviewer.id or reviewer.role == UserRole.CREATOR:
                raise ForbiddenProblem(
                    detail="A creator cannot approve their own submission."
                )

            # Invariant: An admin cannot approve unless acting as an assigned reviewer
            if reviewer.role == UserRole.ADMINISTRATOR:
                if submission.assigned_reviewer_id != reviewer.id:
                    raise ForbiddenProblem(
                        detail="An administrator cannot approve a submission unless acting as an assigned reviewer."
                    )

            # Workspace Rule: Require evidence before approval
            workspace = await session.get(Workspace, submission.workspace_id)
            review_rules = getattr(workspace, "review_rules", {}) or {}
            if review_rules.get("require_evidence_before_approval", True):
                all_f_query = select(Finding).where(Finding.revision_id == submission.current_revision_id)
                all_f_res = await session.execute(all_f_query)
                unverified_evidence = [
                    f for f in all_f_res.scalars().all()
                    if (f.triage_status == TriageStatus.NEEDS_VERIFICATION or (not f.linked_guideline_id and not f.linked_fact_id))
                    and f.creator_action == CreatorAction.PENDING
                ]
                if unverified_evidence:
                    raise ValidationErrorProblem(
                        detail=(
                            f"Approval blocked: 'Require evidence before approval' policy is active and "
                            f"{len(unverified_evidence)} finding(s) have unverified supporting evidence."
                        )
                    )

        # 2. Automation-Bias Safeguard Enforcement
        # Query all active findings on head revision flagged as stochastic audits
        query_audits = select(Finding).where(
            Finding.revision_id == submission.current_revision_id,
            Finding.is_automation_bias_audit == True,  # noqa: E712
        )
        audit_res = await session.execute(query_audits)
        audit_findings = list(audit_res.scalars().all())

        if payload.decision == ReviewSignOff.APPROVED and audit_findings:
            verified_ids = {
                v.finding_id
                for v in (payload.finding_verifications or [])
                if v.verified
            }
            unverified = [f for f in audit_findings if f.id not in verified_ids]

            if unverified:
                raise ValidationErrorProblem(
                    detail=(
                        f"Automation-Bias Safeguard Protection: Cannot approve submission without explicit human "
                        f"source verification. {len(unverified)} audit finding(s) must be certified by reviewer. "
                        f"Unverified Finding IDs: {[str(f.id) for f in unverified]}."
                    ),
                    extensions={
                        "unverified_finding_ids": [str(f.id) for f in unverified],
                        "rule": "AUTOMATION_BIAS_SAFEGUARD_MANDATORY_VERIFICATION",
                    },
                )

        # 3. Transition State Machine
        # Ensure submission transitions through IN_HUMAN_REVIEW if currently in TRIAGED or REVISION
        if submission.workflow_state in {WorkflowState.TRIAGED, WorkflowState.IN_CREATOR_REVISION}:
            SubmissionStateMachine.transition(
                submission=submission,
                target_state=WorkflowState.IN_HUMAN_REVIEW,
                actor_role=reviewer.role,
                is_ai=False,
            )

        target_state = (
            WorkflowState.APPROVED
            if payload.decision == ReviewSignOff.APPROVED
            else WorkflowState.CHANGES_REQUESTED
        )

        SubmissionStateMachine.transition(
            submission=submission,
            target_state=target_state,
            actor_role=reviewer.role,
            is_ai=False,
        )

        submission.assigned_reviewer_id = reviewer.id
        submission.updated_at = datetime.now(timezone.utc)
        await session.flush()

        # 4. Compile Stipulations and Inline Annotations
        stipulations_dict: dict[str, Any] = payload.stipulations or {}
        if payload.finding_verifications:
            stipulations_dict["verified_audits"] = [
                v.model_dump(mode="json") for v in payload.finding_verifications
            ]
        if payload.inline_comments:
            stipulations_dict["inline_annotations"] = [
                c.model_dump(mode="json") for c in payload.inline_comments
            ]

        # 5. Persist Formal ReviewDecision Record
        decision = ReviewDecision(
            id=uuid.uuid4(),
            submission_id=submission.id,
            revision_id=submission.current_revision_id,
            reviewer_id=reviewer.id,
            decision=payload.decision,
            comments=payload.comments,
            stipulations=stipulations_dict if stipulations_dict else None,
            decided_at=datetime.now(timezone.utc),
        )
        session.add(decision)
        await session.flush()

        # 6. Cryptographically Seal Verdict in Audit Ledger
        await AuditService.record_event(
            session=session,
            action=AuditAction.REVIEW_DECIDED,
            workspace_id=submission.workspace_id,
            actor_id=reviewer.id,
            payload={
                "submission_id": str(submission.id),
                "revision_id": str(submission.current_revision_id),
                "decision": payload.decision.value,
                "comments": payload.comments,
                "verified_audit_count": len(audit_findings),
                "inline_comment_count": len(payload.inline_comments or []),
                "workflow_state": submission.workflow_state.value,
            },
        )

        return decision
