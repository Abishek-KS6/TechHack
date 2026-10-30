"""
BrandShield AI - Enterprise Database Idempotent Seeder.
Populates:
1. Multi-tenant Enterprise Workspace: "Acme FinTech Global" (slug: "acme-fintech")
2. Three RBAC Demo Users: Creator, Reviewer, and Administrator (Argon2id password hashes)
3. Rich Brand Profile: "Acme FinTech Global Profile" with tone bounds and privacy gate
4. Twenty (20) Approved Brand Guidelines covering Tone, Terminology, Messaging, Accessibility
5. Fifteen (15) Dated Approved Facts (including 4 intentionally expired facts for staleness testing)
6. Pre-warmed Demo Fallback Cache entries for sub-30ms offline demonstrations
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import math
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.domain.enums import (
    GuidelineCategory,
    SeverityLevel,
    UserRole,
)
from app.infrastructure.db.models import (
    ApprovedFact,
    BrandGuideline,
    BrandProfile,
    User,
    Workspace,
)
from app.infrastructure.db.session import AsyncSessionLocal
from app.services.analysis.demo_fallback_cache import DemoFallbackCache, FallbackLLMResponse


def generate_embedding(text: str, dim: int = 1536) -> list[float]:
    """Generates a deterministic unit-normalized 1536-dim vector for pgvector indexing."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [float(h[i % len(h)]) * math.sin(i + 1) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [round(x / norm, 6) for x in raw]


async def seed_database(session: AsyncSession) -> dict[str, Any]:
    """
    Executes idempotent seeding of the enterprise BrandShield AI demonstration dataset.
    Can be run repeatedly without duplicating unique entities.
    """
    now = datetime.now(timezone.utc)
    demo_password = hash_password("DemoSecure2026!")

    # ==========================================================================
    # 1. Enterprise Workspace
    # ==========================================================================
    w_query = select(Workspace).where(Workspace.slug == "acme-fintech")
    w_res = await session.execute(w_query)
    workspace = w_res.scalars().first()

    if not workspace:
        workspace = Workspace(
            id=uuid.uuid4(),
            name="Acme FinTech Global",
            slug="acme-fintech",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(workspace)
        await session.flush()

    # ==========================================================================
    # 2. Three RBAC Demo Users
    # ==========================================================================
    user_definitions = [
        ("creator@acmefintech.com", "Alex Creator", UserRole.CREATOR),
        ("reviewer@acmefintech.com", "Morgan Reviewer", UserRole.REVIEWER),
        ("admin@acmefintech.com", "Sam Admin", UserRole.ADMINISTRATOR),
        ("creator@acme.com", "Alex Creator", UserRole.CREATOR),
        ("reviewer@acme.com", "Morgan Reviewer", UserRole.REVIEWER),
        ("admin@acme.com", "Sam Admin", UserRole.ADMINISTRATOR),
    ]

    users_by_role: dict[UserRole, User] = {}
    for email, full_name, role in user_definitions:
        u_query = select(User).where(
            User.workspace_id == workspace.id,
            User.email == email,
        )
        u_res = await session.execute(u_query)
        user = u_res.scalars().first()

        if not user:
            user = User(
                id=uuid.uuid4(),
                workspace_id=workspace.id,
                email=email,
                hashed_password=demo_password,
                full_name=full_name,
                role=role,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            await session.flush()

        users_by_role[role] = user

    # ==========================================================================
    # 3. Rich Brand Profile ("Acme FinTech Global Profile")
    # ==========================================================================
    bp_query = select(BrandProfile).where(
        BrandProfile.workspace_id == workspace.id,
        BrandProfile.name == "Acme FinTech Global Profile",
    )
    bp_res = await session.execute(bp_query)
    brand_profile = bp_res.scalars().first()

    if not brand_profile:
        brand_profile = BrandProfile(
            id=uuid.uuid4(),
            workspace_id=workspace.id,
            name="Acme FinTech Global Profile",
            description="Enterprise compliance, terminology matrix, and privacy policy for Acme FinTech Global.",
            tone_parameters={
                "target_formality": 8.0,
                "max_grade_level": 12.0,
                "max_passive_voice_ratio": 0.15,
                "forbidden_sentiments": ["hyperbolic", "casual_slang", "hype"],
            },
            banned_terminology_map={
                "cure": {
                    "reason": "Medical metaphors prohibited in financial technology documentation.",
                    "severity": "HIGH",
                    "suggested_replacements": ["mitigate", "resolve"],
                },
                "crypto casino": {
                    "reason": "Prohibited gambling and high-risk speculative terminology.",
                    "severity": "CRITICAL",
                    "suggested_replacements": ["digital asset platform"],
                },
                "foolproof": {
                    "reason": "Absolute infallibility claim prohibited under SEC rules.",
                    "severity": "HIGH",
                    "suggested_replacements": ["resilient", "robust"],
                },
                "risk-free": {
                    "reason": "Absolute risk-free guarantees prohibited in investment products.",
                    "severity": "CRITICAL",
                    "suggested_replacements": ["hedged", "managed-risk"],
                },
                "100% risk-free": {
                    "reason": "Prohibited absolute superlative risk-free guarantee.",
                    "severity": "CRITICAL",
                    "suggested_replacements": ["institutionally hedged", "risk-managed"],
                },
                "guaranteed monopoly": {
                    "reason": "Unlawful antitrust and anti-competitive guarantee.",
                    "severity": "CRITICAL",
                    "suggested_replacements": ["industry leadership", "strong market presence"],
                },
                "unbeatable": {
                    "reason": "Unsubstantiated competitive superlative.",
                    "severity": "HIGH",
                    "suggested_replacements": ["competitive", "high-value"],
                },
                "guaranteed returns": {
                    "reason": "Strictly illegal return promise under FINRA and SEC standards.",
                    "severity": "CRITICAL",
                    "suggested_replacements": ["targeted yields", "historical yields"],
                },
            },
            preferred_terminology_map={
                "Acme FinTech": {
                    "approved_term": "Acme FinTech™",
                    "reason": "Requires trademark registration symbol on primary brand mention.",
                    "severity": "HIGH",
                },
                "cheap": {
                    "approved_term": "cost-effective",
                    "reason": "Maintain executive positioning.",
                    "severity": "MEDIUM",
                },
                "fast": {
                    "approved_term": "high-throughput",
                    "reason": "Maintain technical authority.",
                    "severity": "LOW",
                },
            },
            messaging_rules={
                "required_disclaimers": ["Past performance is not indicative of future results.", "Investments are subject to market risk."],
                "regulatory_framework": "SEC / FINRA / FTC",
            },
            privacy_gate_config={
                "allow_external_llm": False,
                "approved_providers": ["Azure OpenAI (Zero-Data-Retention)", "Anthropic (Commercial VPC)"],
                "retention_days": 30,
            },
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(brand_profile)
        await session.flush()

    # ==========================================================================
    # 4. Twenty (20) Approved Brand Guidelines
    # ==========================================================================
    guideline_definitions = [
        # --- Tone (5 guidelines) ---
        (
            "ACME-TONE-01",
            "Maintain an authoritative, objective B2B executive tone. Target formality score of 8/10 or higher across all commercial documentation.",
            GuidelineCategory.TONE,
            SeverityLevel.MEDIUM,
        ),
        (
            "ACME-TONE-02",
            "Favor active voice construction. Passive voice must not exceed 15% of total sentence count in any document section.",
            GuidelineCategory.TONE,
            SeverityLevel.LOW,
        ),
        (
            "ACME-TONE-03",
            "Avoid speculative hedging language such as 'we think', 'maybe', or 'we hope' in product capability statements.",
            GuidelineCategory.TONE,
            SeverityLevel.MEDIUM,
        ),
        (
            "ACME-TONE-04",
            "Prohibit hyperbolic promotional slang and informal colloquialisms such as 'crazy', 'insane', or 'blown away'.",
            GuidelineCategory.TONE,
            SeverityLevel.HIGH,
        ),
        (
            "ACME-TONE-05",
            "Keep sentences concise and structured. Sentences exceeding 35 words must be decomposed for clarity.",
            GuidelineCategory.TONE,
            SeverityLevel.LOW,
        ),
        # --- Terminology (5 guidelines) ---
        (
            "ACME-TERM-01",
            "All references to the primary brand 'Acme FinTech' must incorporate the trademark symbol 'Acme FinTech™'.",
            GuidelineCategory.TERMINOLOGY,
            SeverityLevel.HIGH,
        ),
        (
            "ACME-TERM-02",
            "Medical and therapeutic metaphors (e.g., 'cure', 'panacea', 'antidote') are strictly prohibited in technical whitepapers.",
            GuidelineCategory.TERMINOLOGY,
            SeverityLevel.HIGH,
        ),
        (
            "ACME-TERM-03",
            "Gambling and uncalibrated speculative terminology (e.g., 'crypto casino', 'jackpot') are prohibited across all public channels.",
            GuidelineCategory.TERMINOLOGY,
            SeverityLevel.CRITICAL,
        ),
        (
            "ACME-TERM-04",
            "Use technical precision terms: substitute 'high-throughput' for 'fast' and 'cost-effective' for 'cheap'.",
            GuidelineCategory.TERMINOLOGY,
            SeverityLevel.LOW,
        ),
        (
            "ACME-TERM-05",
            "Absolute infallibility descriptors such as 'foolproof', 'flawless', or 'unmatched' are disallowed under FTC advertising standards.",
            GuidelineCategory.TERMINOLOGY,
            SeverityLevel.HIGH,
        ),
        # --- Messaging (5 guidelines) ---
        (
            "ACME-MSG-01",
            "All quantitative performance claims must be accompanied by the standard disclaimer: 'Past performance is not indicative of future results.'",
            GuidelineCategory.MESSAGING,
            SeverityLevel.CRITICAL,
        ),
        (
            "ACME-MSG-02",
            "Never promise or imply guaranteed yields or 'guaranteed returns'. All investments carry market risk.",
            GuidelineCategory.MESSAGING,
            SeverityLevel.CRITICAL,
        ),
        (
            "ACME-MSG-03",
            "Every quantitative metric cited must directly correspond to an approved, unexpired fact in the compliance registry.",
            GuidelineCategory.MESSAGING,
            SeverityLevel.HIGH,
        ),
        (
            "ACME-MSG-04",
            "Clearly disclose all fee schedules and custodial relationships before executing financial commitments.",
            GuidelineCategory.MESSAGING,
            SeverityLevel.MEDIUM,
        ),
        (
            "ACME-MSG-05",
            "Client privacy policies must highlight zero-trust data segregation and AES-256 encryption at rest.",
            GuidelineCategory.MESSAGING,
            SeverityLevel.HIGH,
        ),
        # --- Accessibility (5 guidelines) ---
        (
            "ACME-ACC-01",
            "Content must maintain a Flesch-Kincaid Grade Level at or below 12.0 to ensure readability for diverse stakeholders.",
            GuidelineCategory.ACCESSIBILITY,
            SeverityLevel.MEDIUM,
        ),
        (
            "ACME-ACC-02",
            "Avoid ALL-CAPS words exceeding 4 letters in running prose to prevent visual fatigue and screen reader misinterpretation.",
            GuidelineCategory.ACCESSIBILITY,
            SeverityLevel.LOW,
        ),
        (
            "ACME-ACC-03",
            "Technical tables must provide clear descriptive column headers and consistent unit identifiers.",
            GuidelineCategory.ACCESSIBILITY,
            SeverityLevel.LOW,
        ),
        (
            "ACME-ACC-04",
            "Provide clear plain-language summaries preceding complex multi-paragraph financial disclosures.",
            GuidelineCategory.ACCESSIBILITY,
            SeverityLevel.MEDIUM,
        ),
        (
            "ACME-ACC-05",
            "Visual charts and diagrams must include contextual textual descriptions and meaningful alt-text equivalents.",
            GuidelineCategory.ACCESSIBILITY,
            SeverityLevel.LOW,
        ),
    ]

    seeded_guidelines_count = 0
    for clause_id, clause_text, cat, sev in guideline_definitions:
        g_query = select(BrandGuideline).where(
            BrandGuideline.brand_profile_id == brand_profile.id,
            BrandGuideline.clause_identifier == clause_id,
        )
        g_res = await session.execute(g_query)
        guideline = g_res.scalars().first()

        if not guideline:
            guideline = BrandGuideline(
                id=uuid.uuid4(),
                brand_profile_id=brand_profile.id,
                clause_identifier=clause_id,
                clause_text=clause_text,
                category=cat,
                severity=sev,
                embedding=generate_embedding(clause_text),
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(guideline)
            seeded_guidelines_count += 1

    await session.flush()

    # ==========================================================================
    # 5. Fifteen (15) Dated Approved Facts (4 Intentionally Expired)
    # ==========================================================================
    owner = users_by_role[UserRole.REVIEWER]

    fact_definitions = [
        # --- 4 Expired Facts (Temporal Staleness Showcase) ---
        (
            "Acme FinTech processes 10,000 transactions per second with 99.9% uptime according to our Q1 2023 audit.",
            "https://acmefintech.com/audits/2023-q1.pdf",
            "Audited throughput verified at 10,000 TPS and 99.9% SLA.",
            datetime(2023, 1, 15, tzinfo=timezone.utc),
            datetime(2023, 12, 31, tzinfo=timezone.utc),  # Expired 2023
        ),
        (
            "Our global user base reached 50,000 active accounts in December 2022 with zero operational losses.",
            "https://acmefintech.com/reports/2022-annual.pdf",
            "Year-end 2022 verified user accounts reached 50,000.",
            datetime(2022, 12, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 1, tzinfo=timezone.utc),  # Expired 2024
        ),
        (
            "Acme FinTech maintains $50M in assets under custody as of our 2023 annual filing.",
            "https://acmefintech.com/filings/2023-annual.pdf",
            "Assets under custody certified at $50 million as of fiscal year 2023.",
            datetime(2023, 6, 1, tzinfo=timezone.utc),
            datetime(2024, 6, 30, tzinfo=timezone.utc),  # Expired 2024
        ),
        (
            "Average client onboarding time was reduced to 4 business days during the 2024 beta program.",
            "https://acmefintech.com/reports/2024-beta.pdf",
            "Beta program client onboarding duration verified at 4 business days.",
            datetime(2024, 1, 10, tzinfo=timezone.utc),
            datetime(2024, 12, 31, tzinfo=timezone.utc),  # Expired 2024
        ),
        # --- 11 Active Verified Facts ---
        (
            "Acme FinTech™ infrastructure is certified compliant with SOC 2 Type II and ISO 27001 standards.",
            "https://acmefintech.com/certifications/soc2.pdf",
            "Current SOC 2 Type II certification verified through 2028.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2028, 12, 31, tzinfo=timezone.utc),
        ),
        (
            "The transaction processing engine operates under asynchronous event loops to maintain low latency.",
            "https://acmefintech.com/architecture/whitepaper.pdf",
            "Event-driven architecture verified for non-blocking I/O execution.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2028, 12, 31, tzinfo=timezone.utc),
        ),
        (
            "All client data at rest is encrypted using AES-256 and audit trails are recorded in a SHA-256 tamper-evident ledger.",
            "https://acmefintech.com/security/cryptography.pdf",
            "AES-256 encryption at rest and Merkle audit chain verification.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2028, 12, 31, tzinfo=timezone.utc),
        ),
        (
            "Acme FinTech operates secondary redundant data centers across two distinct geographical regions.",
            "https://acmefintech.com/infrastructure/redundancy.pdf",
            "Dual-region active-passive failover infrastructure verified.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2028, 12, 31, tzinfo=timezone.utc),
        ),
        (
            "Capital at risk. Past performance is not indicative of future results.",
            "https://acmefintech.com/disclosures/general.pdf",
            "Standard mandatory regulatory disclosure statement.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2028, 12, 31, tzinfo=timezone.utc),
        ),
        (
            "Acme FinTech™ supports multi-currency settlement in USD, EUR, and GBP for verified enterprise accounts.",
            "https://acmefintech.com/products/settlement.pdf",
            "Tri-currency clearing and settlement capabilities certified.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2028, 12, 31, tzinfo=timezone.utc),
        ),
        (
            "The platform enforces strict zero-trust role-based access control with Argon2id password hashing.",
            "https://acmefintech.com/security/rbac.pdf",
            "Argon2id hashing with minimum 64MB memory cost verified.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2028, 12, 31, tzinfo=timezone.utc),
        ),
        (
            "Acme FinTech API responses maintain a 99th percentile processing time under 50 milliseconds for cached endpoints.",
            "https://acmefintech.com/telemetry/p99-report.pdf",
            "P99 latency benchmarks verified under 50ms across production endpoints.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2028, 12, 31, tzinfo=timezone.utc),
        ),
        (
            "All automated triage findings provide exact character offsets and direct links to approved guidelines or facts.",
            "https://acmefintech.com/compliance/engine-audit.pdf",
            "Offset-preserving AST span tokenizer and evidence-linked citations.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2028, 12, 31, tzinfo=timezone.utc),
        ),
        (
            "The zero-trust privacy gate scrubs PII before any approved external model invocation.",
            "https://acmefintech.com/privacy/gate-architecture.pdf",
            "Deterministic regex PII scrubber verified before egress routing.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2028, 12, 31, tzinfo=timezone.utc),
        ),
        (
            "Human compliance reviewers retain unilateral approval authority over all content revisions.",
            "https://acmefintech.com/governance/fsm-specification.pdf",
            "FSM state machine strictly prohibits AI from executing final approval.",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2028, 12, 31, tzinfo=timezone.utc),
        ),
    ]

    seeded_facts_count = 0
    for stmt, src_url, excerpt, v_date, exp_date in fact_definitions:
        f_query = select(ApprovedFact).where(
            ApprovedFact.workspace_id == workspace.id,
            ApprovedFact.fact_statement == stmt,
        )
        f_res = await session.execute(f_query)
        fact = f_res.scalars().first()

        if not fact:
            fact = ApprovedFact(
                id=uuid.uuid4(),
                workspace_id=workspace.id,
                fact_statement=stmt,
                original_source_url=src_url,
                evidence_excerpt=excerpt,
                verification_date=v_date,
                last_updated_date=v_date,
                expiry_date=exp_date,
                responsible_owner_id=owner.id,
                embedding=generate_embedding(stmt),
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(fact)
            seeded_facts_count += 1

    await session.flush()

    # ==========================================================================
    # 6. Pre-warmed Demo Fallback Cache
    # ==========================================================================
    demo_phrases = [
        (
            "Our revolutionary AI platform guarantees 100% cure for revenue stagnation.",
            FallbackLLMResponse(
                category="TONE",
                severity="HIGH",
                confidence=0.94,
                explanation="Uses medical metaphors ('100% cure') and uncalibrated superlatives that create legal exposure under FTC truth-in-advertising standards.",
                suggested_rewrite="Our enterprise AI platform is designed to accelerate sustainable revenue growth.",
                sentiment_score=0.88,
                formality_score=4.2,
                flags=["SUPERLATIVE", "METAPHOR_MISUSE"],
            ),
        ),
        (
            "Customers are blown away by our unmatched speed and zero downtime.",
            FallbackLLMResponse(
                category="TONE",
                severity="MEDIUM",
                confidence=0.89,
                explanation="Informal colloquialism ('blown away') diverges from the target B2B executive formality threshold (target 8/10).",
                suggested_rewrite="Enterprise clients report significant latency reductions and exceptional reliability.",
                sentiment_score=0.91,
                formality_score=3.5,
                flags=["INFORMAL_COLLOQUIALISM"],
            ),
        ),
        (
            "We deliver guaranteed returns with 100% zero downtime and infallible fraud detection.",
            FallbackLLMResponse(
                category="MESSAGING",
                severity="CRITICAL",
                confidence=0.98,
                explanation="Strictly prohibited return promise and absolute infallible zero downtime claim under SEC regulations.",
                suggested_rewrite="We offer high-availability architecture designed for financial resilience.",
                sentiment_score=0.90,
                formality_score=5.0,
                flags=["PROHIBITED_GUARANTEE"],
            ),
        ),
    ]

    for phrase, resp in demo_phrases:
        DemoFallbackCache.register_response(phrase, resp)

    await session.commit()

    return {
        "status": "SUCCESS",
        "workspace": {"id": str(workspace.id), "name": workspace.name, "slug": workspace.slug},
        "users": [
            {"email": u.email, "role": u.role.value, "full_name": u.full_name}
            for u in users_by_role.values()
        ],
        "brand_profile": {"id": str(brand_profile.id), "name": brand_profile.name},
        "guidelines_count": len(guideline_definitions),
        "newly_seeded_guidelines": seeded_guidelines_count,
        "facts_count": len(fact_definitions),
        "newly_seeded_facts": seeded_facts_count,
        "expired_facts_count": 4,
        "prewarmed_cache_entries": DemoFallbackCache.get_cache_size(),
    }


async def main():
    """CLI entrypoint for running the seeder."""
    async with AsyncSessionLocal() as session:
        result = await seed_database(session)
        print("BrandShield AI Seeding Complete:")
        for k, v in result.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
