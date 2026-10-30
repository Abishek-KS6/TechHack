"""
BrandShield AI - Stage 4 Confidence Triage & Multi-Stage Intelligence Orchestrator.
Orchestrates the four core intelligence stages:
1. Stage 1 - Deterministic Rule Engine (Aho-Corasick, FKGL, Passive Voice, Caps Abuse).
2. Stage 2 - Temporal Fact & Hybrid RAG Retrieval Engine (RRF, Staleness, Missing Evidence).
3. Stage 3 - Privacy-Gated Boundary & Circuit-Breaker LLM Router (PII Scrubber, Fallback Cache).
4. Stage 4 - Confidence Triage Boundaries & 15% Stochastic Automation-Bias Safeguard.
"""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime, timezone
import random
import time
from typing import Any, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import (
    AuditAction,
    CreatorAction,
    DetectorSource,
    FindingCategory,
    TriageStatus,
    WorkflowState,
)
from app.infrastructure.db.models import (
    ApprovedFact,
    BrandGuideline,
    BrandProfile,
    DocumentRevision,
    Finding,
    Submission,
    Workspace,
)
from app.services.analysis.deterministic_engine import DeterministicRuleEngine
from app.services.analysis.privacy_gate import PrivacyGateRouter
from app.services.analysis.temporal_fact_engine import TemporalFactEngine
from app.services.audit_service import AuditService

settings = get_settings()

AUTOMATION_BIAS_SAMPLE_RATE = getattr(settings, "AUTOMATION_BIAS_SAMPLE_RATE", 0.15)


@dataclass
class AnalysisPipelineResult:
    """Summary metrics and persisted detections from the 4-stage intelligence pipeline."""
    revision_id: uuid.UUID
    total_findings: int
    flagged_high_confidence: int
    routed_to_human_low_confidence: int
    stale_facts_to_reverify: int
    needs_verification_missing_evidence: int
    automation_bias_audits_injected: int
    processing_duration_ms: float
    findings: list[Finding] = field(default_factory=list)


class TriageOrchestrator:
    """
    Master Intelligence Pipeline Orchestrator for BrandShield AI.
    Executes deterministic checks first, anchors factual assertions in verified temporal ground truth,
    applies privacy-gated external routing, and routes findings through calibrated confidence tiers.
    """

    @classmethod
    def evaluate_automation_bias_safeguard(
        cls,
        sampling_rate: float = AUTOMATION_BIAS_SAMPLE_RATE,
        rng: Optional[random.Random] = None,
    ) -> bool:
        """Evaluates whether finding should undergo shadow audit injection."""
        generator = rng or random
        return generator.random() < sampling_rate

    @classmethod
    async def run_pipeline(
        cls,
        session: AsyncSession,
        revision_id: uuid.UUID,
        brand_profile_id: uuid.UUID,
        workspace_id: uuid.UUID,
        content_text: str,
        requested_provider: str = "Azure OpenAI",
        preloaded_profile: Optional[BrandProfile] = None,
        preloaded_guidelines: Optional[list[BrandGuideline]] = None,
        preloaded_facts: Optional[list[ApprovedFact]] = None,
        audit_sample_rate: float = AUTOMATION_BIAS_SAMPLE_RATE,
        rng: Optional[random.Random] = None,
    ) -> AnalysisPipelineResult:
        """
        Executes end-to-end 4-stage analysis pipeline and persists findings with audit trails.
        """
        start_time = time.perf_counter()

        # ----------------------------------------------------------------------
        # 0. Resolve Entity Context
        # ----------------------------------------------------------------------
        profile = preloaded_profile
        if not profile:
            profile = await session.get(BrandProfile, brand_profile_id)
            if not profile:
                raise ValueError(f"Brand profile {brand_profile_id} not found.")

        guidelines = preloaded_guidelines
        if guidelines is None:
            g_query = select(BrandGuideline).where(
                BrandGuideline.brand_profile_id == brand_profile_id,
                BrandGuideline.is_active == True,  # noqa: E712
            )
            g_res = await session.execute(g_query)
            guidelines = list(g_res.scalars().all())

        # Resolve Workspace Review Rules
        ws = await session.get(Workspace, workspace_id)
        ws_rules = getattr(ws, "review_rules", {}) or {}
        conf_threshold = float(ws_rules.get("confidence_threshold", 0.85))
        effective_sample_rate = audit_sample_rate
        if audit_sample_rate == AUTOMATION_BIAS_SAMPLE_RATE and "random_double_check_percentage" in ws_rules:
            effective_sample_rate = float(ws_rules["random_double_check_percentage"]) / 100.0

        # ----------------------------------------------------------------------
        # Stage 1 (L1 In-Memory Automaton) & Stage 2 (Temporal Fact Hybrid RAG)
        # Executed concurrently via asyncio.gather for sub-millisecond triage
        # ----------------------------------------------------------------------
        stage1_task = asyncio.to_thread(
            DeterministicRuleEngine.analyze_document,
            content_text=content_text,
            brand_profile=profile,
            guidelines=guidelines,
        )
        stage2_task = TemporalFactEngine.evaluate_claims(
            content_text=content_text,
            workspace_id=workspace_id,
            session=session,
            preloaded_facts=preloaded_facts,
        )
        deterministic_hits, temporal_hits = await asyncio.gather(stage1_task, stage2_task)

        # ----------------------------------------------------------------------
        # Stage 3: Privacy Gate & Circuit-Breaker LLM Router
        # ----------------------------------------------------------------------
        tone_hits = await PrivacyGateRouter.analyze_tone_and_messaging(
            content_text=content_text,
            brand_profile=profile,
            workspace_id=workspace_id,
            session=session,
            requested_provider=requested_provider,
        )

        # ----------------------------------------------------------------------
        # Stage 4: Confidence Triage & 15% Automation-Bias Safeguard
        # ----------------------------------------------------------------------
        raw_finding_records: list[Finding] = []
        now = datetime.now(timezone.utc)

        # 4A. Ingest Deterministic Hits (Always 1.0 confidence, FLAGGED_HIGH_CONFIDENCE)
        for d in deterministic_hits:
            f = Finding(
                id=uuid.uuid4(),
                revision_id=revision_id,
                issue_category=d.issue_category,
                severity=d.severity,
                confidence_score=1.0,
                triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
                start_offset=d.start_offset,
                end_offset=d.end_offset,
                explanation_reason=d.explanation_reason,
                suggested_correction=d.suggested_correction,
                linked_guideline_id=d.linked_guideline_id,
                linked_fact_id=None,
                detector_source=DetectorSource.DETERMINISTIC_RULE,
                is_automation_bias_audit=False,
                creator_action=CreatorAction.PENDING,
                created_at=now,
                updated_at=now,
            )
            raw_finding_records.append(f)

        # 4B. Ingest Temporal Fact Hits
        for t in temporal_hits:
            f = Finding(
                id=uuid.uuid4(),
                revision_id=revision_id,
                issue_category=t.issue_category,
                severity=t.severity,
                confidence_score=t.confidence_score,
                triage_status=t.triage_status,
                start_offset=t.start_offset,
                end_offset=t.end_offset,
                explanation_reason=t.explanation_reason,
                suggested_correction=t.suggested_correction,
                linked_guideline_id=None,
                linked_fact_id=t.linked_fact_id,
                detector_source=DetectorSource.TEMPORAL_FACT_MATCHER,
                is_automation_bias_audit=False,
                creator_action=CreatorAction.PENDING,
                created_at=now,
                updated_at=now,
            )
            raw_finding_records.append(f)

        # 4C. Ingest and Triage External LLM Tone Hits
        for tone in tone_hits:
            # Calibrated Confidence Gating:
            # - score >= 0.85 AND valid link -> FLAGGED_HIGH_CONFIDENCE
            # - 0.40 <= score < 0.85 -> ROUTED_TO_HUMAN_LOW_CONFIDENCE
            # - score < 0.40 -> Suppressed
            if tone.confidence_score < 0.40:
                continue

            linked_g_id = tone.linked_guideline_id
            if not linked_g_id and guidelines:
                for g in guidelines:
                    cat_val = g.category.value if hasattr(g.category, "value") else str(g.category)
                    if cat_val in (tone.issue_category.value, FindingCategory.TONE.value, FindingCategory.MESSAGING.value):
                        linked_g_id = g.id
                        break

            linked_f_id = tone.linked_fact_id
            has_valid_link = (linked_g_id is not None) or (linked_f_id is not None)

            if not has_valid_link:
                status = TriageStatus.NEEDS_VERIFICATION
            elif tone.confidence_score >= conf_threshold:
                status = TriageStatus.FLAGGED_HIGH_CONFIDENCE
            else:
                status = TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE

            f = Finding(
                id=uuid.uuid4(),
                revision_id=revision_id,
                issue_category=tone.issue_category,
                severity=tone.severity,
                confidence_score=tone.confidence_score,
                triage_status=status,
                start_offset=tone.start_offset,
                end_offset=tone.end_offset,
                explanation_reason=tone.explanation_reason,
                suggested_correction=tone.suggested_correction,
                linked_guideline_id=linked_g_id,
                linked_fact_id=linked_f_id,
                detector_source=tone.detector_source,
                is_automation_bias_audit=False,
                creator_action=CreatorAction.PENDING,
                created_at=now,
                updated_at=now,
            )
            raw_finding_records.append(f)

        # ----------------------------------------------------------------------
        # 4D. Automation-Bias Safeguard (15% Stochastic Shadow Audit)
        # ----------------------------------------------------------------------
        audit_count = 0
        high_conf_findings = [
            f for f in raw_finding_records
            if f.triage_status == TriageStatus.FLAGGED_HIGH_CONFIDENCE
        ]

        rand_gen = rng or random
        for finding in high_conf_findings:
            if rand_gen.random() < effective_sample_rate:
                finding.is_automation_bias_audit = True
                finding.explanation_reason = (
                    "[AUTOMATION-BIAS SAFEGUARD: Human verification of primary evidence citation mandatory before approval] "
                    + finding.explanation_reason
                )
                audit_count += 1

                # Log shadow audit injection into immutable ledger
                await AuditService.record_event(
                    session=session,
                    action=AuditAction.STOCHASTIC_AUDIT_INJECTED,
                    workspace_id=workspace_id,
                    payload={
                        "finding_id": str(finding.id),
                        "revision_id": str(revision_id),
                        "detector_source": finding.detector_source.value,
                        "category": finding.issue_category.value,
                        "sampling_rate": audit_sample_rate,
                    },
                )

        # ----------------------------------------------------------------------
        # 5. Persist Findings & Update Submission State Machine
        # ----------------------------------------------------------------------
        for f in raw_finding_records:
            session.add(f)
        await session.flush()

        # Update root submission state to TRIAGED
        rev = await session.get(DocumentRevision, revision_id)
        if rev:
            sub = await session.get(Submission, rev.submission_id)
            if sub:
                sub.workflow_state = WorkflowState.TRIAGED
                await session.flush()

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Record pipeline completion in cryptographic audit ledger
        await AuditService.record_event(
            session=session,
            action=AuditAction.ANALYSIS_PIPELINE_EXECUTED,
            workspace_id=workspace_id,
            payload={
                "revision_id": str(revision_id),
                "total_findings": len(raw_finding_records),
                "deterministic_count": len(deterministic_hits),
                "temporal_count": len(temporal_hits),
                "tone_count": len(tone_hits),
                "automation_bias_audits": audit_count,
                "duration_ms": duration_ms,
            },
        )
        await session.commit()

        # Compile metric tallies
        cnt_high = sum(1 for f in raw_finding_records if f.triage_status == TriageStatus.FLAGGED_HIGH_CONFIDENCE)
        cnt_low = sum(1 for f in raw_finding_records if f.triage_status == TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE)
        cnt_stale = sum(1 for f in raw_finding_records if f.triage_status == TriageStatus.STALE_FACT_REVERIFY)
        cnt_missing = sum(1 for f in raw_finding_records if f.triage_status == TriageStatus.NEEDS_VERIFICATION_MISSING_EVIDENCE)

        return AnalysisPipelineResult(
            revision_id=revision_id,
            total_findings=len(raw_finding_records),
            flagged_high_confidence=cnt_high,
            routed_to_human_low_confidence=cnt_low,
            stale_facts_to_reverify=cnt_stale,
            needs_verification_missing_evidence=cnt_missing,
            automation_bias_audits_injected=audit_count,
            processing_duration_ms=duration_ms,
            findings=raw_finding_records,
        )

    @classmethod
    async def stream_pipeline(
        cls,
        session: AsyncSession,
        revision_id: uuid.UUID,
        brand_profile_id: uuid.UUID,
        workspace_id: uuid.UUID,
        content_text: str,
        requested_provider: str = "Azure OpenAI",
        preloaded_profile: Optional[BrandProfile] = None,
        preloaded_guidelines: Optional[list[BrandGuideline]] = None,
        preloaded_facts: Optional[list[ApprovedFact]] = None,
        audit_sample_rate: float = AUTOMATION_BIAS_SAMPLE_RATE,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Executes the 4-stage intelligence pipeline while streaming real-time stage progress
        with millisecond latencies via an async generator for Server-Sent Events (SSE).
        """
        start_time = time.perf_counter()

        # 0. Resolve Entity Context
        profile = preloaded_profile
        if not profile:
            profile = await session.get(BrandProfile, brand_profile_id)
            if not profile:
                raise ValueError(f"Brand profile {brand_profile_id} not found.")

        guidelines = preloaded_guidelines
        if guidelines is None:
            g_query = select(BrandGuideline).where(
                BrandGuideline.brand_profile_id == brand_profile_id,
                BrandGuideline.is_active == True,  # noqa: E712
            )
            g_res = await session.execute(g_query)
            guidelines = list(g_res.scalars().all())

        # Resolve Workspace Review Rules
        ws = await session.get(Workspace, workspace_id)
        ws_rules = getattr(ws, "review_rules", {}) or {}
        conf_threshold = float(ws_rules.get("confidence_threshold", 0.85))
        effective_sample_rate = audit_sample_rate
        if audit_sample_rate == AUTOMATION_BIAS_SAMPLE_RATE and "random_double_check_percentage" in ws_rules:
            effective_sample_rate = float(ws_rules["random_double_check_percentage"]) / 100.0

        # ----------------------------------------------------------------------
        # Stage 1: Deterministic Rule Engine (O(N) Aho-Corasick & Readability)
        # ----------------------------------------------------------------------
        t1_start = time.perf_counter()
        deterministic_hits = DeterministicRuleEngine.analyze_document(
            content_text=content_text,
            brand_profile=profile,
            guidelines=guidelines,
        )
        t1_ms = round((time.perf_counter() - t1_start) * 1000, 2)
        yield {
            "event": "STAGE_1_DETERMINISTIC_COMPLETE",
            "data": {
                "stage": "STAGE_1_DETERMINISTIC_COMPLETE",
                "latency_ms": t1_ms,
                "findings_count": len(deterministic_hits),
                "summary": f"Detected {len(deterministic_hits)} deterministic rule violation(s)",
            },
        }

        # ----------------------------------------------------------------------
        # Stage 2: Temporal Fact & Hybrid RAG Retrieval Engine
        # ----------------------------------------------------------------------
        t2_start = time.perf_counter()
        temporal_hits = await TemporalFactEngine.evaluate_claims(
            content_text=content_text,
            workspace_id=workspace_id,
            session=session,
            preloaded_facts=preloaded_facts,
        )
        t2_ms = round((time.perf_counter() - t2_start) * 1000, 2)
        cnt_stale = sum(1 for t in temporal_hits if t.triage_status == TriageStatus.STALE_FACT_REVERIFY)
        cnt_missing = sum(1 for t in temporal_hits if t.triage_status == TriageStatus.NEEDS_VERIFICATION_MISSING_EVIDENCE)
        yield {
            "event": "STAGE_2_TEMPORAL_FACT_RAG_COMPLETE",
            "data": {
                "stage": "STAGE_2_TEMPORAL_FACT_RAG_COMPLETE",
                "latency_ms": t2_ms,
                "temporal_claims_count": len(temporal_hits),
                "stale_facts": cnt_stale,
                "missing_evidence": cnt_missing,
                "summary": f"Evaluated claims: {cnt_stale} stale facts, {cnt_missing} ungrounded claims",
            },
        }

        # ----------------------------------------------------------------------
        # Stage 3: Privacy Gate & Circuit-Breaker LLM Router
        # ----------------------------------------------------------------------
        t3_start = time.perf_counter()
        tone_hits = await PrivacyGateRouter.analyze_tone_and_messaging(
            content_text=content_text,
            brand_profile=profile,
            workspace_id=workspace_id,
            session=session,
            requested_provider=requested_provider,
        )
        t3_ms = round((time.perf_counter() - t3_start) * 1000, 2)
        yield {
            "event": "STAGE_3_PRIVACY_GATE_VERIFIED",
            "data": {
                "stage": "STAGE_3_PRIVACY_GATE_VERIFIED",
                "latency_ms": t3_ms,
                "provider": requested_provider,
                "tone_hits_count": len(tone_hits),
                "pii_redacted": True,
                "summary": f"Privacy gate verified with {requested_provider}; {len(tone_hits)} tone anomalies detected",
            },
        }

        # ----------------------------------------------------------------------
        # Stage 4: Confidence Triage & 15% Automation-Bias Safeguard
        # ----------------------------------------------------------------------
        t4_start = time.perf_counter()
        raw_finding_records: list[Finding] = []
        now = datetime.now(timezone.utc)

        ws_stream = await session.get(Workspace, workspace_id)
        ws_rules_stream = getattr(ws_stream, "review_rules", {}) or {}
        conf_threshold_stream = float(ws_rules_stream.get("confidence_threshold", 0.85))
        effective_sample_rate_stream = audit_sample_rate
        if audit_sample_rate == AUTOMATION_BIAS_SAMPLE_RATE and "random_double_check_percentage" in ws_rules_stream:
            effective_sample_rate_stream = float(ws_rules_stream["random_double_check_percentage"]) / 100.0

        # 4A. Ingest Deterministic Hits
        for d in deterministic_hits:
            f = Finding(
                id=uuid.uuid4(),
                revision_id=revision_id,
                issue_category=d.issue_category,
                severity=d.severity,
                confidence_score=1.0,
                triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
                start_offset=d.start_offset,
                end_offset=d.end_offset,
                explanation_reason=d.explanation_reason,
                suggested_correction=d.suggested_correction,
                linked_guideline_id=d.linked_guideline_id,
                linked_fact_id=None,
                detector_source=DetectorSource.DETERMINISTIC_RULE,
                is_automation_bias_audit=False,
                creator_action=CreatorAction.PENDING,
                created_at=now,
                updated_at=now,
            )
            raw_finding_records.append(f)

        # 4B. Ingest Temporal Fact Hits
        for t in temporal_hits:
            f = Finding(
                id=uuid.uuid4(),
                revision_id=revision_id,
                issue_category=t.issue_category,
                severity=t.severity,
                confidence_score=t.confidence_score,
                triage_status=t.triage_status,
                start_offset=t.start_offset,
                end_offset=t.end_offset,
                explanation_reason=t.explanation_reason,
                suggested_correction=t.suggested_correction,
                linked_guideline_id=None,
                linked_fact_id=t.linked_fact_id,
                detector_source=DetectorSource.TEMPORAL_FACT_MATCHER,
                is_automation_bias_audit=False,
                creator_action=CreatorAction.PENDING,
                created_at=now,
                updated_at=now,
            )
            raw_finding_records.append(f)

        # 4C. Ingest and Triage External LLM Tone Hits
        for tone in tone_hits:
            if tone.confidence_score < 0.40:
                continue

            linked_g_id = tone.linked_guideline_id
            if not linked_g_id and guidelines:
                for g in guidelines:
                    cat_val = g.category.value if hasattr(g.category, "value") else str(g.category)
                    if cat_val in (tone.issue_category.value, FindingCategory.TONE.value, FindingCategory.MESSAGING.value):
                        linked_g_id = g.id
                        break

            if tone.confidence_score >= conf_threshold_stream and linked_g_id:
                status = TriageStatus.FLAGGED_HIGH_CONFIDENCE
            else:
                status = TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE

            f = Finding(
                id=uuid.uuid4(),
                revision_id=revision_id,
                issue_category=tone.issue_category,
                severity=tone.severity,
                confidence_score=tone.confidence_score,
                triage_status=status,
                start_offset=tone.start_offset,
                end_offset=tone.end_offset,
                explanation_reason=tone.explanation_reason,
                suggested_correction=tone.suggested_correction,
                linked_guideline_id=linked_g_id,
                linked_fact_id=None,
                detector_source=tone.detector_source or DetectorSource.EXTERNAL_LLM,
                is_automation_bias_audit=False,
                creator_action=CreatorAction.PENDING,
                created_at=now,
                updated_at=now,
            )
            raw_finding_records.append(f)

        # 4D. 15% Stochastic Automation-Bias Safeguard
        audit_count = 0
        if effective_sample_rate_stream > 0.0:
            for finding in raw_finding_records:
                if (
                    finding.triage_status == TriageStatus.FLAGGED_HIGH_CONFIDENCE
                    and random.random() < effective_sample_rate_stream
                ):
                    finding.triage_status = TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE
                    finding.is_automation_bias_audit = True
                    audit_count += 1
                    await AuditService.record_event(
                        session=session,
                        action=AuditAction.STOCHASTIC_AUDIT_INJECTED,
                        workspace_id=workspace_id,
                        payload={
                            "finding_id": str(finding.id),
                            "category": finding.issue_category.value,
                            "sampling_rate": audit_sample_rate,
                        },
                    )

        # 5. Persist Findings & Update Submission State Machine
        for f in raw_finding_records:
            session.add(f)
        await session.flush()

        rev = await session.get(DocumentRevision, revision_id)
        if rev:
            sub = await session.get(Submission, rev.submission_id)
            if sub:
                sub.workflow_state = WorkflowState.TRIAGED
                await session.flush()

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        t4_ms = round((time.perf_counter() - t4_start) * 1000, 2)

        await AuditService.record_event(
            session=session,
            action=AuditAction.ANALYSIS_PIPELINE_EXECUTED,
            workspace_id=workspace_id,
            payload={
                "revision_id": str(revision_id),
                "total_findings": len(raw_finding_records),
                "deterministic_count": len(deterministic_hits),
                "temporal_count": len(temporal_hits),
                "tone_count": len(tone_hits),
                "automation_bias_audits": audit_count,
                "duration_ms": duration_ms,
            },
        )
        await session.commit()

        cnt_high = sum(1 for f in raw_finding_records if f.triage_status == TriageStatus.FLAGGED_HIGH_CONFIDENCE)
        cnt_low = sum(1 for f in raw_finding_records if f.triage_status == TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE)
        cnt_stale = sum(1 for f in raw_finding_records if f.triage_status == TriageStatus.STALE_FACT_REVERIFY)
        cnt_missing = sum(1 for f in raw_finding_records if f.triage_status == TriageStatus.NEEDS_VERIFICATION_MISSING_EVIDENCE)

        yield {
            "event": "STAGE_4_TRIAGE_COMPLETE",
            "data": {
                "stage": "STAGE_4_TRIAGE_COMPLETE",
                "latency_ms": t4_ms,
                "total_findings": len(raw_finding_records),
                "high_confidence": cnt_high,
                "routed_to_human": cnt_low,
                "stale_facts": cnt_stale,
                "missing_evidence": cnt_missing,
                "automation_bias_audits": audit_count,
            },
        }

        # Final Event
        yield {
            "event": "PIPELINE_COMPLETE",
            "data": {
                "stage": "PIPELINE_COMPLETE",
                "status": "SUCCESS",
                "revision_id": str(revision_id),
                "total_findings": len(raw_finding_records),
                "duration_ms": duration_ms,
                "findings": [
                    {
                        "id": str(f.id),
                        "issue_category": f.issue_category.value,
                        "severity": f.severity.value,
                        "confidence_score": f.confidence_score,
                        "triage_status": f.triage_status.value,
                        "start_offset": f.start_offset,
                        "end_offset": f.end_offset,
                        "explanation_reason": f.explanation_reason,
                        "suggested_correction": f.suggested_correction,
                    }
                    for f in raw_finding_records
                ],
            },
        }


# Alias for backward compatibility
AnalysisTriageOrchestrator = TriageOrchestrator
