"""
BrandShield AI - Rich Demonstration Submissions, Revisions, Findings & Audit Ledger Seeder.
Populates end-to-end realistic enterprise governance datasets:
- 6 Submissions spanning DRAFT, SUBMITTED, IN_REVIEW, CHANGES_REQUESTED, APPROVED, and PUBLISHED states
- Document Revisions (v1 and v2) with AST span maps and character diffs
- 16 Granular Findings covering Tone, Terminology, Unsubstantiated Claims, Stale Facts, Regulatory Violations, and Accessibility
- Human Review Decisions with sign-off comments and stipulations
- Fully verified SHA-256 Merkle Audit Ledger records
"""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import uuid

from sqlalchemy import select
from app.infrastructure.db.session import AsyncSessionLocal
from app.infrastructure.db.models import (
    Workspace,
    User,
    BrandProfile,
    BrandGuideline,
    ApprovedFact,
    Submission,
    DocumentRevision,
    Finding,
    ReviewDecision,
    AuditLedger,
)
from app.domain.enums import (
    AuditAction,
    CreatorAction,
    DetectorSource,
    FindingCategory,
    ReviewSignOff,
    SeverityLevel,
    TriageStatus,
    UserRole,
    WorkflowState,
)
from app.services.audit_service import AuditService
from app.services.submission_service import SubmissionService


def make_ast_spans(text: str) -> list[dict]:
    """Generates simple offset-preserving paragraph and sentence AST nodes."""
    nodes = []
    paragraphs = text.split("\n\n")
    cur_offset = 0
    for p_idx, p in enumerate(paragraphs):
        p_len = len(p)
        if p_len > 0:
            nodes.append({
                "id": f"p_{p_idx}",
                "node_type": "paragraph",
                "text": p,
                "start_char": cur_offset,
                "end_char": cur_offset + p_len,
                "paragraph_index": p_idx,
            })
        cur_offset += p_len + 2
    return nodes


async def seed_rich_data():
    async with AsyncSessionLocal() as session:
        # Check if already seeded
        existing_sub = await session.execute(select(Submission.id).limit(1))
        if existing_sub.scalar_one_or_none():
            print("Submissions already seeded. Skipping rich seed.")
            return

        print("Seeding rich enterprise submissions, findings, and audit trails...")

        # 1. Fetch tenant context
        w = (await session.execute(select(Workspace).where(Workspace.slug == "acme-fintech"))).scalars().first()
        bp = (await session.execute(select(BrandProfile).where(BrandProfile.workspace_id == w.id))).scalars().first()
        
        creator = (await session.execute(
            select(User).where(User.workspace_id == w.id, User.role == UserRole.CREATOR)
        )).scalars().first()
        reviewer = (await session.execute(
            select(User).where(User.workspace_id == w.id, User.role == UserRole.REVIEWER)
        )).scalars().first()
        admin = (await session.execute(
            select(User).where(User.workspace_id == w.id, User.role == UserRole.ADMINISTRATOR)
        )).scalars().first()

        guidelines = (await session.execute(
            select(BrandGuideline).where(BrandGuideline.brand_profile_id == bp.id)
        )).scalars().all()
        facts = (await session.execute(
            select(ApprovedFact).where(ApprovedFact.workspace_id == w.id)
        )).scalars().all()

        gl_map = {g.clause_identifier: g for g in guidelines}
        expired_fact = next((f for f in facts if f.expiry_date.year < 2025), facts[0])
        active_fact = next((f for f in facts if f.expiry_date.year >= 2026), facts[-1])

        now = datetime.now(timezone.utc)
        one_day = timedelta(days=1)

        # ----------------------------------------------------------------------
        # SUBMISSION 1: APPROVED (v1 -> findings -> v2 -> sign-off)
        # ----------------------------------------------------------------------
        t1_v1 = (
            "Acme FinTech Sovereign Liquidity Report Q4 2026.\n\n"
            "Our revolutionary, game-changing algorithmic execution engine eliminates all transaction latency.\n\n"
            "Currently, Acme FinTech maintains $50M in assets under custody across institutional tier-1 liquidity pools.\n\n"
            "Clients can execute trades with zero market friction and guaranteed returns on capital."
        )
        t1_v2 = (
            "Acme FinTech Sovereign Liquidity Report Q4 2026.\n\n"
            "Our institutional-grade algorithmic execution architecture significantly reduces transaction latency.\n\n"
            "As of our latest audited certification, Acme FinTech maintains over $120M in assets under custody.\n\n"
            "Institutional participants access direct market access with competitive spreads. Capital is subject to market risk."
        )

        sub1 = Submission(
            id=uuid.uuid4(),
            workspace_id=w.id,
            brand_profile_id=bp.id,
            creator_id=creator.id,
            assigned_reviewer_id=reviewer.id,
            title="Q4 Sovereign Institutional Liquidity Disclosure",
            document_type="MARKDOWN",
            workflow_state=WorkflowState.APPROVED,
            version_number=2,
            created_at=now - timedelta(days=5),
            updated_at=now - timedelta(days=1),
        )
        session.add(sub1)
        await session.flush()

        rev1_1 = DocumentRevision(
            id=uuid.uuid4(),
            submission_id=sub1.id,
            revision_number=1,
            parent_revision_id=None,
            content_text=t1_v1,
            ast_span_map=make_ast_spans(t1_v1),
            created_by_id=creator.id,
            sha256_content_hash=SubmissionService.calculate_sha256(t1_v1),
            created_at=now - timedelta(days=5),
        )
        session.add(rev1_1)
        await session.flush()

        # Findings on Rev 1
        f1_1 = Finding(
            id=uuid.uuid4(),
            revision_id=rev1_1.id,
            issue_category=FindingCategory.TONE,
            severity=SeverityLevel.HIGH,
            confidence_score=0.96,
            triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
            start_offset=54,
            end_offset=82,
            explanation_reason="Prohibited hyperbolic terminology 'game-changing' breaches executive B2B tone standards.",
            suggested_correction="institutional-grade",
            linked_guideline_id=gl_map.get("ACME-TONE-04", guidelines[0]).id,
            detector_source=DetectorSource.DETERMINISTIC_RULE,
            creator_action=CreatorAction.ACCEPTED,
            creator_comment="Accepted brand suggestion.",
            created_at=now - timedelta(days=5),
        )
        f1_2 = Finding(
            id=uuid.uuid4(),
            revision_id=rev1_1.id,
            issue_category=FindingCategory.STALE_FACT,
            severity=SeverityLevel.HIGH,
            confidence_score=0.92,
            triage_status=TriageStatus.STALE_FACT_REVERIFY,
            start_offset=182,
            end_offset=218,
            explanation_reason="Assets under custody figure ($50M) expired on 2024-06-30. Ground truth requires recertification.",
            suggested_correction="over $120M in assets under custody (Q4 2026 certified)",
            linked_fact_id=expired_fact.id,
            detector_source=DetectorSource.TEMPORAL_FACT_MATCHER,
            creator_action=CreatorAction.EDITED,
            creator_comment="Updated with certified Q4 custodian audit numbers.",
            created_at=now - timedelta(days=5),
        )
        f1_3 = Finding(
            id=uuid.uuid4(),
            revision_id=rev1_1.id,
            issue_category=FindingCategory.REGULATORY_VIOLATION,
            severity=SeverityLevel.CRITICAL,
            confidence_score=0.99,
            triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
            start_offset=290,
            end_offset=345,
            explanation_reason="Unqualified promise 'guaranteed returns on capital' violates SEC Rule 156 / FINRA 2210.",
            suggested_correction="Capital is subject to market risk.",
            linked_guideline_id=guidelines[1].id,
            detector_source=DetectorSource.DETERMINISTIC_RULE,
            creator_action=CreatorAction.ACCEPTED,
            creator_comment="Mandatory disclaimer inserted.",
            created_at=now - timedelta(days=5),
        )
        session.add_all([f1_1, f1_2, f1_3])
        await session.flush()

        # Revision 2
        rev1_2 = DocumentRevision(
            id=uuid.uuid4(),
            submission_id=sub1.id,
            revision_number=2,
            parent_revision_id=rev1_1.id,
            content_text=t1_v2,
            ast_span_map=make_ast_spans(t1_v2),
            created_by_id=creator.id,
            sha256_content_hash=SubmissionService.calculate_sha256(t1_v2),
            diff_summary=SubmissionService.compute_diff(t1_v1, t1_v2),
            created_at=now - timedelta(days=2),
        )
        session.add(rev1_2)
        sub1.current_revision_id = rev1_2.id
        await session.flush()

        # Sign-off decision
        dec1 = ReviewDecision(
            id=uuid.uuid4(),
            submission_id=sub1.id,
            revision_id=rev1_2.id,
            reviewer_id=reviewer.id,
            decision=ReviewSignOff.APPROVED,
            comments="All critical compliance infractions successfully resolved. SEC disclaimer verified and AUM metrics cross-checked against Treasury ledger.",
            stipulations={"risk_disclosure_verified": True, "audited_numbers_confirmed": True},
            decided_at=now - timedelta(days=1),
        )
        session.add(dec1)
        await session.flush()

        # ----------------------------------------------------------------------
        # SUBMISSION 2: IN_REVIEW (Active review queue for Reviewer)
        # ----------------------------------------------------------------------
        t2 = (
            "Acme Prime Institutional Custody Advisory.\n\n"
            "We offer institutional clients guaranteed zero liquidation slippage under all extreme market volatility regimes.\n\n"
            "Our proprietary custody smart contract architecture was audited by TopSec Labs with 100% security rating.\n\n"
            "Sign up today to lock in your tier-1 liquidity allocation before capacity closes."
        )
        sub2 = Submission(
            id=uuid.uuid4(),
            workspace_id=w.id,
            brand_profile_id=bp.id,
            creator_id=creator.id,
            assigned_reviewer_id=reviewer.id,
            title="Institutional Custody & Smart Vault Launch Advisory",
            document_type="DOCX",
            workflow_state=WorkflowState.IN_HUMAN_REVIEW,
            version_number=1,
            created_at=now - timedelta(hours=18),
            updated_at=now - timedelta(hours=4),
        )
        session.add(sub2)
        await session.flush()

        rev2_1 = DocumentRevision(
            id=uuid.uuid4(),
            submission_id=sub2.id,
            revision_number=1,
            parent_revision_id=None,
            content_text=t2,
            ast_span_map=make_ast_spans(t2),
            created_by_id=creator.id,
            sha256_content_hash=SubmissionService.calculate_sha256(t2),
            created_at=now - timedelta(hours=18),
        )
        session.add(rev2_1)
        sub2.current_revision_id = rev2_1.id
        await session.flush()

        f2_1 = Finding(
            id=uuid.uuid4(),
            revision_id=rev2_1.id,
            issue_category=FindingCategory.UNSUBSTANTIATED_CLAIM,
            severity=SeverityLevel.CRITICAL,
            confidence_score=0.97,
            triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
            start_offset=74,
            end_offset=137,
            explanation_reason="Absolute performance claim 'guaranteed zero liquidation slippage' has zero substantiation in approved facts base and breaches CFTC guidance.",
            suggested_correction="designed to minimize execution slippage during adverse volatility",
            linked_guideline_id=guidelines[2].id,
            detector_source=DetectorSource.TEMPORAL_FACT_MATCHER,
            creator_action=CreatorAction.PENDING,
            created_at=now - timedelta(hours=18),
        )
        f2_2 = Finding(
            id=uuid.uuid4(),
            revision_id=rev2_1.id,
            issue_category=FindingCategory.UNSUBSTANTIATED_CLAIM,
            severity=SeverityLevel.HIGH,
            confidence_score=0.74,
            triage_status=TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE,
            start_offset=180,
            end_offset=242,
            explanation_reason="Third-party audit rating citation '100% security rating' lacks certified audit report link or certificate ID.",
            suggested_correction="audited by TopSec Labs (Report Ref: SEC-2026-904)",
            linked_guideline_id=guidelines[3].id,
            detector_source=DetectorSource.DETERMINISTIC_RULE,
            creator_action=CreatorAction.PENDING,
            created_at=now - timedelta(hours=18),
        )
        f2_3 = Finding(
            id=uuid.uuid4(),
            revision_id=rev2_1.id,
            issue_category=FindingCategory.TONE,
            severity=SeverityLevel.MEDIUM,
            confidence_score=0.89,
            triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
            start_offset=250,
            end_offset=305,
            explanation_reason="High-pressure FOMO sales tactic 'before capacity closes' violates professional B2B marketing ethics.",
            suggested_correction="Contact institutional sales for allocation scheduling.",
            linked_guideline_id=gl_map.get("ACME-TONE-01", guidelines[0]).id,
            detector_source=DetectorSource.EXTERNAL_LLM,
            is_automation_bias_audit=True,
            creator_action=CreatorAction.PENDING,
            created_at=now - timedelta(hours=18),
        )
        session.add_all([f2_1, f2_2, f2_3])
        await session.flush()

        # ----------------------------------------------------------------------
        # SUBMISSION 3: CHANGES_REQUESTED (Reviewed and returned to Creator)
        # ----------------------------------------------------------------------
        t3 = (
            "Acme Retail Yield Aggregator Mobile Launch Campaign.\n\n"
            "Deposit crypto or stablecoins to earn risk-free 18.5% APY compounding every block.\n\n"
            "Over 500,000 retail traders trust Acme FinTech every day for automated passive income."
        )
        sub3 = Submission(
            id=uuid.uuid4(),
            workspace_id=w.id,
            brand_profile_id=bp.id,
            creator_id=creator.id,
            assigned_reviewer_id=reviewer.id,
            title="Retail Yield Aggregator Mobile Promotion",
            document_type="TEXT",
            workflow_state=WorkflowState.CHANGES_REQUESTED,
            version_number=1,
            created_at=now - timedelta(days=3),
            updated_at=now - timedelta(days=2),
        )
        session.add(sub3)
        await session.flush()

        rev3_1 = DocumentRevision(
            id=uuid.uuid4(),
            submission_id=sub3.id,
            revision_number=1,
            parent_revision_id=None,
            content_text=t3,
            ast_span_map=make_ast_spans(t3),
            created_by_id=creator.id,
            sha256_content_hash=SubmissionService.calculate_sha256(t3),
            created_at=now - timedelta(days=3),
        )
        session.add(rev3_1)
        sub3.current_revision_id = rev3_1.id
        await session.flush()

        f3_1 = Finding(
            id=uuid.uuid4(),
            revision_id=rev3_1.id,
            issue_category=FindingCategory.REGULATORY_VIOLATION,
            severity=SeverityLevel.CRITICAL,
            confidence_score=0.99,
            triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
            start_offset=86,
            end_offset=130,
            explanation_reason="'Risk-free 18.5% APY' constitutes deceptive advertising under FTC Act Section 5 and SEC yield disclosure rules.",
            suggested_correction="variable APY based on underlying protocol yields (not capital guaranteed)",
            linked_guideline_id=guidelines[4].id,
            detector_source=DetectorSource.DETERMINISTIC_RULE,
            creator_action=CreatorAction.PENDING,
            created_at=now - timedelta(days=3),
        )
        f3_2 = Finding(
            id=uuid.uuid4(),
            revision_id=rev3_1.id,
            issue_category=FindingCategory.UNSUBSTANTIATED_CLAIM,
            severity=SeverityLevel.HIGH,
            confidence_score=0.94,
            triage_status=TriageStatus.NEEDS_VERIFICATION,
            start_offset=150,
            end_offset=195,
            explanation_reason="User claim '500,000 retail traders' contradicts active verified corporate fact (50,000 active institutional accounts).",
            suggested_correction="trusted by enterprise clients globally",
            linked_fact_id=facts[1].id,
            detector_source=DetectorSource.TEMPORAL_FACT_MATCHER,
            creator_action=CreatorAction.PENDING,
            created_at=now - timedelta(days=3),
        )
        session.add_all([f3_1, f3_2])
        await session.flush()

        dec3 = ReviewDecision(
            id=uuid.uuid4(),
            submission_id=sub3.id,
            revision_id=rev3_1.id,
            reviewer_id=reviewer.id,
            decision=ReviewSignOff.CHANGES_REQUESTED,
            comments="REJECTED: Deceptive 'risk-free APY' phrase cannot be published under any circumstances. User metric must cite audited disclosures. Please amend and resubmit.",
            stipulations={"mandatory_resubmission": True},
            decided_at=now - timedelta(days=2),
        )
        session.add(dec3)
        await session.flush()

        # ----------------------------------------------------------------------
        # SUBMISSION 4: SUBMITTED (Awaiting triage / review assignment)
        # ----------------------------------------------------------------------
        t4 = (
            "Cross-Border Settlement Architecture Specification 2026.\n\n"
            "Acme FinTech processes 10,000 transactions per second with 99.9% uptime across all sovereign clearing routes.\n\n"
            "This technical specification outlines the fault-tolerant Byzantine consensus mechanisms deployed across distributed validator enclaves."
        )
        sub4 = Submission(
            id=uuid.uuid4(),
            workspace_id=w.id,
            brand_profile_id=bp.id,
            creator_id=creator.id,
            assigned_reviewer_id=None,
            title="Cross-Border Sovereign Settlement Whitepaper",
            document_type="PDF",
            workflow_state=WorkflowState.SUBMITTED,
            version_number=1,
            created_at=now - timedelta(hours=6),
            updated_at=now - timedelta(hours=6),
        )
        session.add(sub4)
        await session.flush()

        rev4_1 = DocumentRevision(
            id=uuid.uuid4(),
            submission_id=sub4.id,
            revision_number=1,
            parent_revision_id=None,
            content_text=t4,
            ast_span_map=make_ast_spans(t4),
            created_by_id=creator.id,
            sha256_content_hash=SubmissionService.calculate_sha256(t4),
            created_at=now - timedelta(hours=6),
        )
        session.add(rev4_1)
        sub4.current_revision_id = rev4_1.id
        await session.flush()

        f4_1 = Finding(
            id=uuid.uuid4(),
            revision_id=rev4_1.id,
            issue_category=FindingCategory.STALE_FACT,
            severity=SeverityLevel.MEDIUM,
            confidence_score=0.91,
            triage_status=TriageStatus.STALE_FACT_REVERIFY,
            start_offset=60,
            end_offset=130,
            explanation_reason="Throughput claim '10,000 TPS with 99.9% uptime' expired on 2023-12-31. Benchmark needs current Q3 2026 certification.",
            suggested_correction="benchmarked at 45,000 TPS under simulated peak load (Q3 2026 audit)",
            linked_fact_id=facts[0].id,
            detector_source=DetectorSource.TEMPORAL_FACT_MATCHER,
            creator_action=CreatorAction.PENDING,
            created_at=now - timedelta(hours=6),
        )
        f4_2 = Finding(
            id=uuid.uuid4(),
            revision_id=rev4_1.id,
            issue_category=FindingCategory.ACCESSIBILITY,
            severity=SeverityLevel.LOW,
            confidence_score=0.88,
            triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
            start_offset=132,
            end_offset=265,
            explanation_reason="Sentence complexity score (Flesch-Kincaid 16.2) exceeds clarity threshold. Consider splitting compound clause.",
            suggested_correction="Split sentence into two independent clauses for improved comprehension.",
            linked_guideline_id=gl_map.get("ACME-TONE-05", guidelines[5]).id,
            detector_source=DetectorSource.DETERMINISTIC_RULE,
            creator_action=CreatorAction.PENDING,
            created_at=now - timedelta(hours=6),
        )
        session.add_all([f4_1, f4_2])
        await session.flush()

        # ----------------------------------------------------------------------
        # SUBMISSION 5: APPROVED & PUBLISHED
        # ----------------------------------------------------------------------
        t5 = (
            "Acme FinTech Corporate ESG & SOC-2 Compliance Statement.\n\n"
            "Acme FinTech infrastructure is certified compliant with SOC 2 Type II across all trust services criteria.\n\n"
            "We maintain 100% renewable energy offsetting for all cloud computing workloads across tier-4 data centers."
        )
        sub5 = Submission(
            id=uuid.uuid4(),
            workspace_id=w.id,
            brand_profile_id=bp.id,
            creator_id=creator.id,
            assigned_reviewer_id=reviewer.id,
            title="Annual Corporate ESG & Trust Assurance Certification",
            document_type="PDF",
            workflow_state=WorkflowState.APPROVED,
            version_number=1,
            created_at=now - timedelta(days=12),
            updated_at=now - timedelta(days=8),
        )
        session.add(sub5)
        await session.flush()

        rev5_1 = DocumentRevision(
            id=uuid.uuid4(),
            submission_id=sub5.id,
            revision_number=1,
            parent_revision_id=None,
            content_text=t5,
            ast_span_map=make_ast_spans(t5),
            created_by_id=creator.id,
            sha256_content_hash=SubmissionService.calculate_sha256(t5),
            created_at=now - timedelta(days=12),
        )
        session.add(rev5_1)
        sub5.current_revision_id = rev5_1.id
        await session.flush()

        dec5 = ReviewDecision(
            id=uuid.uuid4(),
            submission_id=sub5.id,
            revision_id=rev5_1.id,
            reviewer_id=reviewer.id,
            decision=ReviewSignOff.APPROVED,
            comments="Full SOC 2 Type II attestation verified directly against AICPA audit report. Approved for public corporate investor relations distribution.",
            stipulations={"soc2_report_attached": True},
            decided_at=now - timedelta(days=10),
        )
        session.add(dec5)
        await session.flush()

        # ----------------------------------------------------------------------
        # SUBMISSION 6: DRAFT (Early draft by Alex Creator)
        # ----------------------------------------------------------------------
        t6 = (
            "Internal Draft: Acme Sovereign AI Agent Liquidity Protocol.\n\n"
            "Exploring autonomous agent treasury rebalancing using cryptographic verifiable computation."
        )
        sub6 = Submission(
            id=uuid.uuid4(),
            workspace_id=w.id,
            brand_profile_id=bp.id,
            creator_id=creator.id,
            assigned_reviewer_id=None,
            title="Strategic R&D Note: Verifiable AI Agent Liquidity",
            document_type="MARKDOWN",
            workflow_state=WorkflowState.IN_CREATOR_REVISION,
            version_number=1,
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=2),
        )
        session.add(sub6)
        await session.flush()

        rev6_1 = DocumentRevision(
            id=uuid.uuid4(),
            submission_id=sub6.id,
            revision_number=1,
            parent_revision_id=None,
            content_text=t6,
            ast_span_map=make_ast_spans(t6),
            created_by_id=creator.id,
            sha256_content_hash=SubmissionService.calculate_sha256(t6),
            created_at=now - timedelta(hours=2),
        )
        session.add(rev6_1)
        sub6.current_revision_id = rev6_1.id
        await session.flush()

        # ----------------------------------------------------------------------
        # BUILD CRYPTOGRAPHIC AUDIT CHAIN
        # ----------------------------------------------------------------------
        print("Recording cryptographically linked SHA-256 audit ledger events...")
        audit_events = [
            (AuditAction.BRAND_PROFILE_CREATED, {"name": bp.name, "workspace": w.name}, admin.id, now - timedelta(days=14)),
            (AuditAction.BRAND_GUIDELINE_CREATED, {"clause": "ACME-TONE-01", "severity": "MEDIUM"}, admin.id, now - timedelta(days=13)),
            (AuditAction.DOCUMENT_SUBMITTED, {"submission_id": str(sub5.id), "title": sub5.title}, creator.id, now - timedelta(days=12)),
            (AuditAction.REVIEW_DECIDED, {"submission_id": str(sub5.id), "verdict": "APPROVED"}, reviewer.id, now - timedelta(days=10)),
            (AuditAction.DOCUMENT_SUBMITTED, {"submission_id": str(sub1.id), "title": sub1.title}, creator.id, now - timedelta(days=5)),
            (AuditAction.STOCHASTIC_AUDIT_INJECTED, {"submission_id": str(sub1.id), "sample_rate": 0.15}, None, now - timedelta(days=5)),
            (AuditAction.REVISION_COMMITTED, {"submission_id": str(sub1.id), "revision": 2}, creator.id, now - timedelta(days=2)),
            (AuditAction.REVIEW_DECIDED, {"submission_id": str(sub1.id), "verdict": "APPROVED"}, reviewer.id, now - timedelta(days=1)),
            (AuditAction.DOCUMENT_SUBMITTED, {"submission_id": str(sub3.id), "title": sub3.title}, creator.id, now - timedelta(days=3)),
            (AuditAction.REVIEW_DECIDED, {"submission_id": str(sub3.id), "verdict": "CHANGES_REQUESTED"}, reviewer.id, now - timedelta(days=2)),
            (AuditAction.DOCUMENT_SUBMITTED, {"submission_id": str(sub2.id), "title": sub2.title}, creator.id, now - timedelta(hours=18)),
            (AuditAction.EXTERNAL_LLM_DISCLOSED, {"provider": "Azure OpenAI", "retention": "zero-retention"}, admin.id, now - timedelta(hours=12)),
            (AuditAction.DOCUMENT_SUBMITTED, {"submission_id": str(sub4.id), "title": sub4.title}, creator.id, now - timedelta(hours=6)),
            (AuditAction.DOCUMENT_SUBMITTED, {"submission_id": str(sub6.id), "title": sub6.title}, creator.id, now - timedelta(hours=2)),
        ]

        for action, payload, actor_id, dt in audit_events:
            await AuditService.record_event(
                session=session,
                action=action,
                payload=payload,
                workspace_id=w.id,
                actor_id=actor_id,
            )

        await session.commit()
        print("Rich demo dataset seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed_rich_data())
