"""
BrandShield AI - Strict Finite State Machine (FSM)
Governs document lifecycle states and enforces non-bypassable human review boundaries.
Guarantees that AI can NEVER approve a submission; only human Reviewers/Administrators can execute final approval.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.core.exceptions import ForbiddenProblem, StateTransitionConflictProblem
from app.domain.enums import UserRole, WorkflowState

if TYPE_CHECKING:
    from app.infrastructure.db.models import Submission


class SubmissionStateMachine:
    """
    Finite State Machine governing the BrandShield submission lifecycle:
    SUBMITTED -> (ANALYZING) -> TRIAGED -> IN_CREATOR_REVISION -> IN_HUMAN_REVIEW -> (APPROVED | CHANGES_REQUESTED)
    """

    # Permitted state transition map
    VALID_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
        WorkflowState.SUBMITTED: {WorkflowState.ANALYZING, WorkflowState.TRIAGED},
        WorkflowState.ANALYZING: {WorkflowState.TRIAGED},
        WorkflowState.TRIAGED: {WorkflowState.IN_CREATOR_REVISION, WorkflowState.IN_HUMAN_REVIEW},
        WorkflowState.IN_CREATOR_REVISION: {WorkflowState.IN_HUMAN_REVIEW, WorkflowState.ANALYZING},
        WorkflowState.IN_HUMAN_REVIEW: {WorkflowState.APPROVED, WorkflowState.CHANGES_REQUESTED},
        WorkflowState.CHANGES_REQUESTED: {WorkflowState.IN_CREATOR_REVISION},
        WorkflowState.APPROVED: set(),  # Terminal state: approved documents cannot be mutated
    }

    # Role constraints for specific state transitions
    ROLE_REQUIREMENTS: dict[WorkflowState, set[UserRole]] = {
        WorkflowState.APPROVED: {UserRole.REVIEWER, UserRole.ADMINISTRATOR},
        WorkflowState.CHANGES_REQUESTED: {UserRole.REVIEWER, UserRole.ADMINISTRATOR},
        WorkflowState.IN_HUMAN_REVIEW: {UserRole.CREATOR, UserRole.ADMINISTRATOR},
        WorkflowState.IN_CREATOR_REVISION: {UserRole.CREATOR, UserRole.ADMINISTRATOR},
    }

    @classmethod
    def can_transition(
        cls,
        current_state: WorkflowState,
        target_state: WorkflowState,
        actor_role: Optional[UserRole] = None,
        is_ai: bool = False,
    ) -> bool:
        """Evaluates whether a state transition is legally permissible without raising exceptions."""
        try:
            cls.validate_transition(
                current_state=current_state,
                target_state=target_state,
                actor_role=actor_role,
                is_ai=is_ai,
            )
            return True
        except Exception:
            return False

    @classmethod
    def validate_transition(
        cls,
        current_state: WorkflowState,
        target_state: WorkflowState,
        actor_role: Optional[UserRole] = None,
        is_ai: bool = False,
    ) -> None:
        """
        Validates state transition legality, raising RFC 7807 problem exceptions on violation:
        1. Target state must be a valid outgoing edge from current_state in the FSM DAG.
        2. Strict AI Safeguard: AI is explicitly forbidden from transitioning to APPROVED.
        3. RBAC Persona Safeguard: Only authorized roles can execute governance sign-offs.
        """
        # 1. Edge validity check
        allowed_targets = cls.VALID_TRANSITIONS.get(current_state, set())
        if target_state not in allowed_targets:
            raise StateTransitionConflictProblem(
                detail=(
                    f"Illegal workflow transition: Cannot move submission from '{current_state.value}' "
                    f"to '{target_state.value}'. Permitted transitions: {[s.value for s in allowed_targets]}."
                ),
                from_state=current_state.value,
                to_state=target_state.value,
                actor_role=actor_role.value if actor_role else "SYSTEM/AI",
            )

        # 2. Hard Governance Rule: AI CAN NEVER APPROVE A SUBMISSION
        if target_state == WorkflowState.APPROVED:
            if is_ai:
                raise ForbiddenProblem(
                    detail="Governance Policy Invariant: Automated AI algorithms are strictly prohibited from issuing final document approval.",
                    required_roles=[UserRole.REVIEWER.value, UserRole.ADMINISTRATOR.value],
                    current_role="AI_AGENT",
                )
            if not actor_role or actor_role not in {UserRole.REVIEWER, UserRole.ADMINISTRATOR}:
                raise ForbiddenProblem(
                    detail="Final approval requires certified compliance authorization (REVIEWER or ADMINISTRATOR role).",
                    required_roles=[UserRole.REVIEWER.value, UserRole.ADMINISTRATOR.value],
                    current_role=actor_role.value if actor_role else "ANONYMOUS",
                )

        # 3. Changes Requested requires Reviewer or Administrator
        if target_state == WorkflowState.CHANGES_REQUESTED:
            if is_ai or not actor_role or actor_role not in {UserRole.REVIEWER, UserRole.ADMINISTRATOR}:
                raise ForbiddenProblem(
                    detail="Requesting revision changes requires human compliance governance (REVIEWER or ADMINISTRATOR role).",
                    required_roles=[UserRole.REVIEWER.value, UserRole.ADMINISTRATOR.value],
                    current_role=actor_role.value if actor_role else "AI_OR_ANONYMOUS",
                )

        # 4. In Human Review requires Creator or Administrator
        if target_state == WorkflowState.IN_HUMAN_REVIEW and not is_ai:
            if actor_role and actor_role not in {UserRole.CREATOR, UserRole.ADMINISTRATOR}:
                raise ForbiddenProblem(
                    detail="Submitting content for human review requires authoring authority (CREATOR or ADMINISTRATOR role).",
                    required_roles=[UserRole.CREATOR.value, UserRole.ADMINISTRATOR.value],
                    current_role=actor_role.value,
                )

    @classmethod
    def transition(
        cls,
        submission: Submission,
        target_state: WorkflowState,
        actor_role: Optional[UserRole] = None,
        is_ai: bool = False,
    ) -> WorkflowState:
        """
        Validates and transitions the submission's workflow state.
        Mutates submission.workflow_state in-place.
        """
        cls.validate_transition(
            current_state=submission.workflow_state,
            target_state=target_state,
            actor_role=actor_role,
            is_ai=is_ai,
        )
        submission.workflow_state = target_state
        return target_state
