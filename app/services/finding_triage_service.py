"""
BrandShield AI - Finding Triage & Automation-Bias Safeguard Engine
Enforces tri-state confidence boundaries and injects stochastic shadow audits to combat reviewer complacency.
"""

from datetime import datetime, timezone
import random
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import (
    AuditAction,
    CreatorAction,
    DetectorSource,
    FindingCategory,
    SeverityLevel,
    TriageStatus,
)
from app.domain.schemas.finding import FindingCreate, FindingUpdateAction
from app.infrastructure.db.models import ApprovedFact, DocumentRevision, Finding
from app.services.audit_service import AuditService

settings = get_settings()


class FindingTriageService:
    """
    Evaluates detector findings, applies confidence gating rules, and executes stochastic audits.
    """

    @staticmethod
    def classify_triage(
        confidence_score: float,
        has_grounding_evidence: bool,
        is_stale_fact: bool,
    ) -> TriageStatus:
        """
        Deterministic tri-state triage classification logic.
        """
        if is_stale_fact:
            return TriageStatus.STALE_FACT_REVERIFY

        if not has_grounding_evidence:
            return TriageStatus.NEEDS_VERIFICATION_MISSING_EVIDENCE

        if confidence_score >= 0.90:
            return TriageStatus.FLAGGED_HIGH_CONFIDENCE

        return TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE

    @classmethod
    async def ingest_finding(
        cls,
        session: AsyncSession,
        payload: FindingCreate,
        workspace_id: uuid.UUID,
    ) -> Finding:
        """
        Persists a detection finding, applies confidence triage, and checks for stochastic audit injection.
        """
        # Validate revision existence
        revision = await session.get(DocumentRevision, payload.revision_id)
        if not revision:
            raise ValueError(f"Revision {payload.revision_id} does not exist.")

        # Temporal check on linked fact if applicable
        is_stale = False
        if payload.linked_fact_id:
            fact = await session.get(ApprovedFact, payload.linked_fact_id)
            if fact and fact.expiry_date < datetime.now(timezone.utc):
                is_stale = True

        has_evidence = bool(payload.linked_guideline_id or payload.linked_fact_id)
        computed_triage = cls.classify_triage(
            confidence_score=payload.confidence_score,
            has_grounding_evidence=has_evidence,
            is_stale_fact=is_stale,
        )

        # Stochastic Audit Injection: Randomly sample 5% to combat automation bias
        is_audit = False
        if random.random() < settings.STOCHASTIC_AUDIT_PROBABILITY:
            is_audit = True
            computed_triage = TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE

        finding = Finding(
            revision_id=payload.revision_id,
            issue_category=payload.issue_category,
            severity=payload.severity,
            confidence_score=payload.confidence_score,
            triage_status=computed_triage,
            start_offset=payload.start_offset,
            end_offset=payload.end_offset,
            explanation_reason=payload.explanation_reason,
            suggested_correction=payload.suggested_correction,
            linked_guideline_id=payload.linked_guideline_id,
            linked_fact_id=payload.linked_fact_id,
            detector_source=payload.detector_source,
            is_automation_bias_audit=is_audit,
            creator_action=CreatorAction.PENDING,
        )
        session.add(finding)
        await session.flush()

        if is_audit:
            await AuditService.record_event(
                session=session,
                action=AuditAction.STOCHASTIC_AUDIT_INJECTED,
                workspace_id=workspace_id,
                payload={
                    "finding_id": str(finding.id),
                    "revision_id": str(revision.id),
                    "category": finding.issue_category.value,
                    "reason": "Synthetic double-check injected to calibrate human review vigilance.",
                },
            )

        return finding

    @classmethod
    async def update_creator_action(
        cls,
        session: AsyncSession,
        finding_id: uuid.UUID,
        actor_id: uuid.UUID,
        workspace_id: uuid.UUID,
        payload: FindingUpdateAction,
    ) -> Finding:
        """
        Records the author's response (ACCEPTED, REJECTED, EDITED) to a finding.
        """
        finding = await session.get(Finding, finding_id)
        if not finding:
            raise ValueError(f"Finding {finding_id} does not exist.")

        finding.creator_action = payload.creator_action
        finding.creator_comment = payload.creator_comment
        await session.flush()

        await AuditService.record_event(
            session=session,
            action=AuditAction.FINDING_ACTION_UPDATED,
            workspace_id=workspace_id,
            actor_id=actor_id,
            payload={
                "finding_id": str(finding.id),
                "revision_id": str(finding.revision_id),
                "action": payload.creator_action.value,
                "comment": payload.creator_comment,
            },
        )
        return finding
