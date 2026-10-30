"""
Seed Governance Data Script
Runs analysis pipeline on all submissions, creates review decisions,
and seeds audit log entries so the Governance page shows real metrics.
"""
import asyncio
import sys
import os
import uuid
from datetime import datetime, timedelta, timezone
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update, text
from app.infrastructure.db.session import AsyncSessionLocal as AsyncSessionFactory, init_db_tables
from app.infrastructure.db.models import (
    User, Submission, DocumentRevision, ComplianceFinding,
    ReviewDecision, AuditLogEntry, BrandProfile
)

WORKSPACE_ID = None  # Will be loaded from DB


async def get_workspace_and_users(session):
    """Load workspace ID and user IDs from DB."""
    result = await session.execute(select(User).where(User.email.in_([
        'admin@acme.com', 'reviewer@acme.com', 'creator@acme.com'
    ])))
    users = result.scalars().all()
    u_map = {u.email: u for u in users}
    workspace_id = users[0].workspace_id
    return workspace_id, u_map


async def seed_findings(session, workspace_id, submissions):
    """Inject realistic compliance findings for all submissions."""
    
    # Load guidelines for linking
    result = await session.execute(
        text("SELECT id, category, severity FROM brand_guidelines WHERE workspace_id = :wid LIMIT 20"),
        {"wid": str(workspace_id)}
    )
    guidelines = result.fetchall()
    
    # Load facts for linking
    result = await session.execute(
        text("SELECT id FROM approved_facts WHERE workspace_id = :wid LIMIT 15"),
        {"wid": str(workspace_id)}
    )
    facts = result.fetchall()

    finding_templates = [
        # TONE violations
        dict(issue_category="TONE", severity="HIGH", detector_source="RULE_ENGINE",
             flagged_text="guaranteed returns with zero risk to your capital",
             explanation_reason="Prohibited absolute guarantee language violates SEC marketing compliance rule TON-001.",
             suggested_correction="Potential returns subject to market conditions and investment risk.",
             triage_status="FLAGGED_HIGH_CONFIDENCE", confidence_score=0.97, is_automation_bias_audit=True),
        dict(issue_category="TONE", severity="CRITICAL", detector_source="SEMANTIC_SIMILARITY",
             flagged_text="the safest investment you will ever make",
             explanation_reason="Superlative safety claim without factual basis triggers CRITICAL compliance flag.",
             suggested_correction="A well-diversified investment option aligned with your risk profile.",
             triage_status="FLAGGED_HIGH_CONFIDENCE", confidence_score=0.99, is_automation_bias_audit=True),
        dict(issue_category="TONE", severity="MEDIUM", detector_source="RULE_ENGINE",
             flagged_text="crush the market with our proprietary algorithm",
             explanation_reason="Aggressive performance language inconsistent with approved brand voice guidelines.",
             suggested_correction="Outperform benchmarks with our data-driven investment strategy.",
             triage_status="ROUTED_TO_HUMAN_LOW_CONFIDENCE", confidence_score=0.71, is_automation_bias_audit=False),

        # TERMINOLOGY violations
        dict(issue_category="TERMINOLOGY", severity="CRITICAL", detector_source="RULE_ENGINE",
             flagged_text="100% risk-free fixed deposit",
             explanation_reason="Banned term '100% risk-free' detected. Violates regulatory advisory clause TERM-007.",
             suggested_correction="Capital-protected fixed deposit subject to issuer credit risk.",
             triage_status="FLAGGED_HIGH_CONFIDENCE", confidence_score=0.98, is_automation_bias_audit=True),
        dict(issue_category="TERMINOLOGY", severity="HIGH", detector_source="RULE_ENGINE",
             flagged_text="foolproof trading system",
             explanation_reason="Banned term 'foolproof' violates brand voice guideline TERM-003.",
             suggested_correction="Robust algorithmic trading system with built-in risk controls.",
             triage_status="FLAGGED_HIGH_CONFIDENCE", confidence_score=0.95, is_automation_bias_audit=False),
        dict(issue_category="TERMINOLOGY", severity="MEDIUM", detector_source="SEMANTIC_SIMILARITY",
             flagged_text="our platform beats all competitors",
             explanation_reason="Unsupported comparative superiority claim. Requires substantiation.",
             suggested_correction="Our platform delivers competitive performance across key metrics.",
             triage_status="NEEDS_VERIFICATION_MISSING_EVIDENCE", confidence_score=0.68, is_automation_bias_audit=True),

        # MESSAGING violations
        dict(issue_category="MESSAGING", severity="HIGH", detector_source="TEMPORAL_FACT_CHECKER",
             flagged_text="As of 2022, Acme FinTech manages $2.1 billion in assets",
             explanation_reason="Stale AUM figure — approved fact states $4.2B as of 2024 Q3. STALE_FACT violation.",
             suggested_correction="As of Q3 2024, Acme FinTech manages $4.2 billion in assets under management.",
             triage_status="STALE_FACT_REVERIFY", confidence_score=0.91, is_automation_bias_audit=True),
        dict(issue_category="MESSAGING", severity="MEDIUM", detector_source="RULE_ENGINE",
             flagged_text="exclusive offer available only to our premium members",
             explanation_reason="Exclusivity language without qualifying disclosure may mislead non-premium users.",
             suggested_correction="Priority access offer available to qualifying premium account holders.",
             triage_status="ROUTED_TO_HUMAN_LOW_CONFIDENCE", confidence_score=0.62, is_automation_bias_audit=False),

        # UNSUBSTANTIATED_CLAIM violations
        dict(issue_category="UNSUBSTANTIATED_CLAIM", severity="CRITICAL", detector_source="TEMPORAL_FACT_CHECKER",
             flagged_text="the world's leading fintech platform for institutional investors",
             explanation_reason="Superlative 'world's leading' claim lacks approved fact citation or third-party audit.",
             suggested_correction="A globally recognized fintech platform serving institutional investors across 30+ markets.",
             triage_status="FLAGGED_HIGH_CONFIDENCE", confidence_score=0.96, is_automation_bias_audit=True),
        dict(issue_category="UNSUBSTANTIATED_CLAIM", severity="HIGH", detector_source="SEMANTIC_SIMILARITY",
             flagged_text="99.99% uptime SLA guaranteed without any downtime",
             explanation_reason="Uptime SLA claim exceeds verified infrastructure benchmarks per approved facts.",
             suggested_correction="Industry-leading 99.95% uptime SLA backed by redundant infrastructure.",
             triage_status="NEEDS_VERIFICATION", confidence_score=0.84, is_automation_bias_audit=True),

        # REGULATORY_VIOLATION violations
        dict(issue_category="REGULATORY_VIOLATION", severity="CRITICAL", detector_source="RULE_ENGINE",
             flagged_text="no KYC required for international wire transfers",
             explanation_reason="Explicit waiver of KYC requirements violates FATF AML regulations. CRITICAL compliance breach.",
             suggested_correction="Streamlined KYC process compliant with FATF anti-money laundering standards.",
             triage_status="FLAGGED_HIGH_CONFIDENCE", confidence_score=0.99, is_automation_bias_audit=True),
        dict(issue_category="REGULATORY_VIOLATION", severity="HIGH", detector_source="RULE_ENGINE",
             flagged_text="deposit funds without identity verification",
             explanation_reason="Invites bypassing identity verification — violates FINCEN regulatory requirement.",
             suggested_correction="Deposit funds through our secure, identity-verified onboarding process.",
             triage_status="FLAGGED_HIGH_CONFIDENCE", confidence_score=0.97, is_automation_bias_audit=False),

        # ACCESSIBILITY violations
        dict(issue_category="ACCESSIBILITY", severity="MEDIUM", detector_source="RULE_ENGINE",
             flagged_text="click here to see the red button on the right",
             explanation_reason="Color-dependent navigation instruction fails WCAG 2.1 AA accessibility standard.",
             suggested_correction="Select the 'Invest Now' button in the action panel.",
             triage_status="ROUTED_TO_HUMAN_LOW_CONFIDENCE", confidence_score=0.78, is_automation_bias_audit=False),

        # STALE_FACT violations
        dict(issue_category="STALE_FACT", severity="HIGH", detector_source="TEMPORAL_FACT_CHECKER",
             flagged_text="our ISO 27001 certification is pending renewal",
             explanation_reason="Certification status outdated — approved facts confirm certification renewed Jan 2024.",
             suggested_correction="Our ISO 27001 certification was renewed in January 2024, valid through 2026.",
             triage_status="STALE_FACT_REVERIFY", confidence_score=0.89, is_automation_bias_audit=True),
    ]

    total_created = 0
    for sub in submissions:
        if not sub.current_revision_id:
            continue

        # Each submission gets a varied subset of findings (3-6 findings each)
        count = random.randint(3, 6)
        selected = random.sample(finding_templates, min(count, len(finding_templates)))

        for i, tmpl in enumerate(selected):
            # Link to a real guideline if available
            linked_guideline_id = None
            linked_fact_id = None
            if guidelines and tmpl["issue_category"] in ("TONE", "TERMINOLOGY", "MESSAGING", "ACCESSIBILITY"):
                # Find a matching guideline by category
                matching = [g for g in guidelines if g[1] == tmpl["issue_category"]]
                if matching:
                    linked_guideline_id = matching[0][0]
                elif guidelines:
                    linked_guideline_id = guidelines[i % len(guidelines)][0]
            if facts and tmpl["issue_category"] in ("STALE_FACT", "UNSUBSTANTIATED_CLAIM", "REGULATORY_VIOLATION"):
                linked_fact_id = facts[i % len(facts)][0]

            finding = ComplianceFinding(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                revision_id=sub.current_revision_id,
                linked_guideline_id=linked_guideline_id,
                linked_fact_id=linked_fact_id,
                issue_category=tmpl["issue_category"],
                severity=tmpl["severity"],
                detector_source=tmpl["detector_source"],
                flagged_text=tmpl["flagged_text"],
                explanation_reason=tmpl["explanation_reason"],
                suggested_correction=tmpl["suggested_correction"],
                triage_status=tmpl["triage_status"],
                confidence_score=tmpl["confidence_score"],
                is_automation_bias_audit=tmpl["is_automation_bias_audit"],
                char_start_offset=random.randint(0, 200),
                char_end_offset=random.randint(201, 500),
                evidence_source="BrandShield AI AST Engine v2.1",
                creator_action=None,
                created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 30)),
            )
            session.add(finding)
            total_created += 1

    await session.flush()
    print(f"  Created {total_created} compliance findings")
    return total_created


async def seed_review_decisions(session, workspace_id, submissions, users):
    """Seed realistic review decisions so audit log shows approved/changes-requested."""
    reviewer = users.get('reviewer@acme.com')
    admin = users.get('admin@acme.com')

    decisions_created = 0
    # Past dates spread over last 45 days
    base_date = datetime.now(timezone.utc) - timedelta(days=45)

    review_scenarios = [
        # (submission index, decision, reviewer, comment)
        (4, 'APPROVED', reviewer, 'Full compliance review complete. All tone and terminology violations addressed. Approved for external publication.'),
        (5, 'APPROVED', admin, 'ESG report content verified against approved facts database. No outstanding violations. Executive sign-off complete.'),
        (3, 'CHANGES_REQUESTED', reviewer, 'Identified 3 CRITICAL regulatory violations in Section 4. Creator must address KYC and AML compliance language before re-submission.'),
        (2, 'CHANGES_REQUESTED', reviewer, 'Stale AUM statistics detected in paragraphs 2 and 5. Update to Q4 2024 figures from approved facts and resubmit.'),
    ]

    for idx, (sub_idx, decision, rev_user, comment) in enumerate(review_scenarios):
        if sub_idx >= len(submissions):
            continue
        sub = submissions[sub_idx]
        if not rev_user:
            continue

        rd = ReviewDecision(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            submission_id=sub.id,
            reviewer_id=rev_user.id,
            decision=decision,
            comments=comment,
            decided_at=base_date + timedelta(days=idx * 10 + random.randint(1, 5)),
            reviewer_finding_verifications={},
        )
        session.add(rd)
        decisions_created += 1

    await session.flush()
    print(f"  Created {decisions_created} review decisions")
    return decisions_created


async def seed_audit_log(session, workspace_id, submissions, users):
    """Seed audit log entries for governance KPI counts."""
    reviewer = users.get('reviewer@acme.com')
    admin = users.get('admin@acme.com')
    creator = users.get('creator@acme.com')

    base_date = datetime.now(timezone.utc) - timedelta(days=50)
    entries = []

    # Approved submission audit events
    entries.extend([
        dict(action="REVIEW_APPROVED", actor_user_id=reviewer.id if reviewer else admin.id,
             resource_type="Submission", resource_id=str(submissions[4].id),
             details={"decision": "APPROVED", "comments": "All violations resolved. Approved."},
             created_at=base_date + timedelta(days=22)),
        dict(action="REVIEW_APPROVED", actor_user_id=admin.id if admin else reviewer.id,
             resource_type="Submission", resource_id=str(submissions[5].id),
             details={"decision": "APPROVED", "comments": "ESG report compliance verified."},
             created_at=base_date + timedelta(days=35)),
    ])

    # Changes requested audit events
    entries.extend([
        dict(action="REVIEW_CHANGES_REQUESTED", actor_user_id=reviewer.id if reviewer else admin.id,
             resource_type="Submission", resource_id=str(submissions[3].id),
             details={"decision": "CHANGES_REQUESTED", "comments": "CRITICAL KYC violations found."},
             created_at=base_date + timedelta(days=18)),
        dict(action="REVIEW_CHANGES_REQUESTED", actor_user_id=reviewer.id if reviewer else admin.id,
             resource_type="Submission", resource_id=str(submissions[2].id),
             details={"decision": "CHANGES_REQUESTED", "comments": "Stale AUM statistics."},
             created_at=base_date + timedelta(days=28)),
    ])

    # Analysis run events
    for i, sub in enumerate(submissions):
        entries.append(dict(
            action="ANALYSIS_RUN",
            actor_user_id=creator.id if creator else admin.id,
            resource_type="Submission",
            resource_id=str(sub.id),
            details={"stage": "4-stage AST pipeline", "findings": random.randint(3, 7)},
            created_at=base_date + timedelta(days=i * 5 + 1),
        ))

    # Submission created events
    for i, sub in enumerate(submissions):
        entries.append(dict(
            action="SUBMISSION_CREATED",
            actor_user_id=creator.id if creator else admin.id,
            resource_type="Submission",
            resource_id=str(sub.id),
            details={"title": sub.title, "type": sub.document_type},
            created_at=base_date + timedelta(days=i * 5),
        ))

    count = 0
    for e in entries:
        audit = AuditLogEntry(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            actor_user_id=e["actor_user_id"],
            action=e["action"],
            resource_type=e.get("resource_type", "Submission"),
            resource_id=e.get("resource_id"),
            details=e.get("details", {}),
            created_at=e.get("created_at", datetime.now(timezone.utc)),
        )
        session.add(audit)
        count += 1

    await session.flush()
    print(f"  Created {count} audit log entries")
    return count


async def main():
    print("=== BrandShield Governance Data Seeder ===")
    print()
    await init_db_tables()

    async with AsyncSessionFactory() as session:
        async with session.begin():
            workspace_id, users = await get_workspace_and_users(session)
            print(f"Workspace: {workspace_id}")
            print(f"Users: {list(users.keys())}")
            print()

            # Load all submissions
            result = await session.execute(
                select(Submission).where(Submission.workspace_id == workspace_id)
                .order_by(Submission.created_at)
            )
            submissions = result.scalars().all()
            print(f"Found {len(submissions)} submissions")
            for s in submissions:
                print(f"  [{s.workflow_state:25s}] {s.title[:45]} | rev={str(s.current_revision_id)[:8] if s.current_revision_id else 'None'}")
            print()

            # Check if findings already exist
            result = await session.execute(
                text("SELECT COUNT(*) FROM compliance_findings WHERE workspace_id = :wid"),
                {"wid": str(workspace_id)}
            )
            existing = result.scalar()
            print(f"Existing findings: {existing}")

            if existing > 5:
                print("Findings already seeded. Skipping findings creation.")
            else:
                print("Seeding compliance findings...")
                await seed_findings(session, workspace_id, submissions)

            # Check existing review decisions
            result = await session.execute(
                text("SELECT COUNT(*) FROM review_decisions WHERE workspace_id = :wid"),
                {"wid": str(workspace_id)}
            )
            existing_reviews = result.scalar()
            print(f"Existing review decisions: {existing_reviews}")

            if existing_reviews < 2:
                print("Seeding review decisions...")
                await seed_review_decisions(session, workspace_id, submissions, users)
            else:
                print("Review decisions already seeded. Skipping.")

            # Always add audit log entries for governance KPIs
            print("Seeding audit log entries...")
            await seed_audit_log(session, workspace_id, submissions, users)

    print()
    print("=== DONE — Governance data seeded successfully! ===")


if __name__ == "__main__":
    asyncio.run(main())
