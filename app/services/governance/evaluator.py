"""
BrandShield AI - Automated Labelled Test Set Evaluator.
Executes the compliance analysis pipeline against 15 realistic corporate content samples
with known ground-truth violations and clean baseline controls.
Computes True Positives, False Positives, False Negatives, Precision, Recall, F1 Score, and P95 latency.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Optional
import uuid

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.governance import EvaluationBenchmarkResponse, EvaluationSampleResult
from app.infrastructure.db.models import ApprovedFact, BrandGuideline, BrandProfile
from app.services.analysis.deterministic_engine import DeterministicRuleEngine
from app.services.analysis.privacy_gate import PrivacyGateRouter
from app.services.analysis.temporal_fact_engine import TemporalFactEngine


@dataclass
class LabelledSample:
    """Ground-truth benchmark test case."""
    sample_id: str
    title: str
    text: str
    ground_truth_categories: list[str] = field(default_factory=list)
    description: str = ""


# Built-in labelled evaluation dataset with 15 realistic corporate content samples
BENCHMARK_TESTSET: list[LabelledSample] = [
    # --------------------------------------------------------------------------
    # Group 1: Outdated Statistics / Temporal Staleness (3 samples)
    # --------------------------------------------------------------------------
    LabelledSample(
        sample_id="BENCH-01",
        title="Outdated Transaction Throughput & Uptime",
        text="Acme FinTech™ processes 10,000 transactions per second with 99.9% uptime according to our Q1 2023 audit.",
        ground_truth_categories=["STALE_FACT"],
        description="Quantitative throughput claim backed by an expired Q1 2023 audit fact.",
    ),
    LabelledSample(
        sample_id="BENCH-02",
        title="Outdated User Growth Metric",
        text="Our global user base reached 50,000 active accounts in December 2022 with zero operational losses.",
        ground_truth_categories=["STALE_FACT"],
        description="Active user count citing expired 2022 statistics.",
    ),
    LabelledSample(
        sample_id="BENCH-03",
        title="Outdated Custody Assets Claim",
        text="Acme FinTech™ maintains $50M in assets under custody as of our 2023 annual filing.",
        ground_truth_categories=["STALE_FACT"],
        description="Custodial asset volume citing expired 2023 financial disclosure.",
    ),

    # --------------------------------------------------------------------------
    # Group 2: Unapproved Superlatives & Guarantees (3 samples)
    # --------------------------------------------------------------------------
    LabelledSample(
        sample_id="BENCH-04",
        title="Unapproved #1 Rank & Speed Superlatives",
        text="Acme FinTech™ offers the #1 fastest and most secure cloud banking infrastructure in the world.",
        ground_truth_categories=["UNSUPPORTED_CLAIM"],
        description="Unsubstantiated competitive superlatives: '#1', 'fastest', and 'most secure'.",
    ),
    LabelledSample(
        sample_id="BENCH-05",
        title="Absolute Infallibility & Zero Downtime Guarantee",
        text="We deliver guaranteed returns with 100% zero downtime and infallible fraud detection.",
        ground_truth_categories=["TERMINOLOGY", "UNSUPPORTED_CLAIM"],
        description="Prohibited absolute guarantees: 'guaranteed returns', '100%', 'zero downtime', 'infallible'.",
    ),
    LabelledSample(
        sample_id="BENCH-06",
        title="Unapproved Competitive Leadership Assertion",
        text="Our unmatched architecture has made us the proven leader across international settlement rails.",
        ground_truth_categories=["UNSUPPORTED_CLAIM"],
        description="Uncalibrated superlatives: 'unmatched' and 'proven leader'.",
    ),

    # --------------------------------------------------------------------------
    # Group 3: Off-Brand Tone & Accessibility Violations (3 samples)
    # --------------------------------------------------------------------------
    LabelledSample(
        sample_id="BENCH-07",
        title="Excessive Passive Voice Construction",
        text="Substantial architectural recalibration was painstakingly implemented wherein system latency was observed to have been reduced.",
        ground_truth_categories=["TONE", "ACCESSIBILITY"],
        description="Off-brand passive voice and high complexity exceeding readability grade thresholds.",
    ),
    LabelledSample(
        sample_id="BENCH-08",
        title="ALL-CAPS Shouting Violation",
        text="WARNING: ALL CLIENT TRANSACTIONS MUST IMMEDIATELY COMPLY WITH MANDATORY SYSTEM UPGRADES TODAY.",
        ground_truth_categories=["ACCESSIBILITY"],
        description="Accessibility breach due to running uppercase words exceeding length thresholds.",
    ),
    LabelledSample(
        sample_id="BENCH-09",
        title="Hyperbolic Colloquial Slang",
        text="Our brand new mobile wallet is totally crazy and crushing it with mind-blowing features.",
        ground_truth_categories=["TONE"],
        description="Informal colloquial slang ('crazy', 'crushing it', 'mind-blowing') violating executive formality.",
    ),

    # --------------------------------------------------------------------------
    # Group 4: Terminology Conflicts & Prohibited Terms (3 samples)
    # --------------------------------------------------------------------------
    LabelledSample(
        sample_id="BENCH-10",
        title="Prohibited Medical Metaphor",
        text="Our proprietary algorithm provides a cure for investment portfolio risk.",
        ground_truth_categories=["TERMINOLOGY"],
        description="Banned medical metaphor 'cure' in financial technology documentation.",
    ),
    LabelledSample(
        sample_id="BENCH-11",
        title="Missing Trademark Attribution",
        text="Deploy Acme FinTech core banking modules across multi-cloud enterprise environments.",
        ground_truth_categories=["TERMINOLOGY"],
        description="Primary brand mention lacking required trademark symbol 'Acme FinTech™'.",
    ),
    LabelledSample(
        sample_id="BENCH-12",
        title="Prohibited High-Risk Gambling Terminology",
        text="Our platform offers a crypto casino feature for high-frequency day traders.",
        ground_truth_categories=["TERMINOLOGY"],
        description="Prohibited high-risk gambling terminology 'crypto casino'.",
    ),

    # --------------------------------------------------------------------------
    # Group 5: Clean Baseline Passages (3 samples)
    # --------------------------------------------------------------------------
    LabelledSample(
        sample_id="BENCH-13",
        title="Clean Baseline Passage 1 - Enterprise Solutions",
        text="Acme FinTech™ provides modern cloud banking solutions designed for business customers.",
        ground_truth_categories=[],
        description="Compliant corporate baseline overview with proper trademark attribution.",
    ),
    LabelledSample(
        sample_id="BENCH-14",
        title="Clean Baseline Passage 2 - Security Architecture",
        text="We protect customer accounts using strict access controls and encrypted audit records.",
        ground_truth_categories=[],
        description="Compliant technical architecture disclosure adhering to objective formality standards.",
    ),
    LabelledSample(
        sample_id="BENCH-15",
        title="Clean Baseline Passage 3 - Mandatory Disclaimer",
        text="Capital at risk. Past performance is not indicative of future results.",
        ground_truth_categories=[],
        description="Compliant regulatory disclosure carrying mandatory investment risk warnings.",
    ),
]


class GovernanceEvaluator:
    """
    Automated benchmark evaluation engine.
    Executes the intelligence pipeline across the 15 ground-truth corporate samples
    and calculates statistical accuracy and latency percentiles.
    """

    @classmethod
    def create_default_benchmark_profile(cls, workspace_id: uuid.UUID) -> BrandProfile:
        """Constructs an in-memory benchmark BrandProfile when none is provisioned in the DB."""
        now = datetime.now(timezone.utc)
        return BrandProfile(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            name="Acme FinTech Global Profile",
            description="Benchmark baseline profile for Acme FinTech Global.",
            tone_parameters={
                "target_formality": 8.0,
                "max_grade_level": 16.0,
                "max_passive_voice_ratio": 0.15,
                "forbidden_sentiments": ["hyperbolic", "casual_slang", "hype"],
            },
            banned_terminology_map={
                "cure": {"reason": "Medical metaphors prohibited in financial infrastructure.", "severity": "HIGH", "suggested_replacements": ["mitigate"]},
                "crypto casino": {"reason": "Prohibited gambling and high-risk terminology.", "severity": "CRITICAL", "suggested_replacements": ["digital asset platform"]},
                "foolproof": {"reason": "Absolute infallibility claim prohibited under SEC rules.", "severity": "HIGH", "suggested_replacements": ["resilient"]},
                "risk-free": {"reason": "Absolute risk-free guarantees prohibited in investment products.", "severity": "CRITICAL", "suggested_replacements": ["hedged"]},
                "unbeatable": {"reason": "Unsubstantiated competitive superlative.", "severity": "HIGH", "suggested_replacements": ["competitive"]},
                "guaranteed returns": {"reason": "Illegal return promise under FINRA and SEC.", "severity": "CRITICAL", "suggested_replacements": ["targeted yields"]},
            },
            preferred_terminology_map={
                "cheap": {"approved_term": "cost-effective", "reason": "Maintain executive positioning.", "severity": "MEDIUM"},
                "fast": {"approved_term": "high-throughput", "reason": "Maintain technical authority.", "severity": "LOW"},
            },
            messaging_rules={
                "required_disclaimers": ["Past performance is not indicative of future results."],
                "required_trademarks": {"Acme FinTech": "Acme FinTech™"},
                "regulatory_framework": "SEC / FINRA / FTC",
            },
            privacy_gate_config={
                "allow_external_llm": False,
                "approved_providers": ["Azure OpenAI"],
                "retention_days": 30,
            },
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def create_default_benchmark_facts(cls, workspace_id: uuid.UUID) -> list[ApprovedFact]:
        """Constructs in-memory facts including the 4 expired facts to demonstrate temporal staleness."""
        now = datetime.now(timezone.utc)
        u_id = uuid.uuid4()
        return [
            # Expired Fact 1
            ApprovedFact(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                fact_statement="Acme FinTech processes 10,000 transactions per second with 99.9% uptime according to our Q1 2023 audit.",
                original_source_url="https://acmefintech.com/audits/2023-q1.pdf",
                evidence_excerpt="Audited throughput verified at 10,000 TPS and 99.9% SLA.",
                verification_date=datetime(2023, 1, 15, tzinfo=timezone.utc),
                expiry_date=datetime(2023, 12, 31, tzinfo=timezone.utc),
                responsible_owner_id=u_id,
                embedding=[0.0] * 1536,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            # Expired Fact 2
            ApprovedFact(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                fact_statement="Our global user base reached 50,000 active accounts in December 2022 with zero operational losses.",
                original_source_url="https://acmefintech.com/reports/2022-annual.pdf",
                evidence_excerpt="Year-end 2022 verified user accounts reached 50,000.",
                verification_date=datetime(2022, 12, 1, tzinfo=timezone.utc),
                expiry_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                responsible_owner_id=u_id,
                embedding=[0.0] * 1536,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            # Expired Fact 3
            ApprovedFact(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                fact_statement="Acme FinTech maintains $50M in assets under custody as of our 2023 annual filing.",
                original_source_url="https://acmefintech.com/filings/2023-annual.pdf",
                evidence_excerpt="Assets under custody certified at $50 million as of fiscal year 2023.",
                verification_date=datetime(2023, 6, 1, tzinfo=timezone.utc),
                expiry_date=datetime(2024, 6, 30, tzinfo=timezone.utc),
                responsible_owner_id=u_id,
                embedding=[0.0] * 1536,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            # Active Fact 4 (Clean control)
            ApprovedFact(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                fact_statement="Capital at risk. Past performance is not indicative of future results.",
                original_source_url="https://acmefintech.com/disclosures/general.pdf",
                evidence_excerpt="Required regulatory investment disclaimer.",
                verification_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                expiry_date=datetime(2028, 12, 31, tzinfo=timezone.utc),
                responsible_owner_id=u_id,
                embedding=[0.0] * 1536,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
        ]

    @classmethod
    async def run_benchmark(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        brand_profile_id: Optional[uuid.UUID] = None,
    ) -> EvaluationBenchmarkResponse:
        """
        Executes benchmark evaluation across all 15 corporate samples.
        Computes precision, recall, F1, and P95 latency.
        """
        evaluated_at = datetime.now(timezone.utc)

        # 1. Resolve BrandProfile
        profile: Optional[BrandProfile] = None
        if session is not None:
            if brand_profile_id:
                try:
                    profile = await session.get(BrandProfile, brand_profile_id)
                except Exception:
                    profile = None
            if not profile:
                try:
                    p_query = select(BrandProfile).where(
                        BrandProfile.workspace_id == workspace_id,
                        BrandProfile.is_active == True,  # noqa: E712
                    )
                    p_res = await session.execute(p_query)
                    scalars = p_res.scalars()
                    profile = scalars.first() if hasattr(scalars, "first") else None
                except Exception:
                    profile = None

        if not profile:
            profile = cls.create_default_benchmark_profile(workspace_id)

        # 2. Resolve Brand Guidelines
        guidelines: list[BrandGuideline] = []
        if session is not None:
            try:
                g_query = select(BrandGuideline).where(
                    BrandGuideline.brand_profile_id == profile.id,
                    BrandGuideline.is_active == True,  # noqa: E712
                )
                g_res = await session.execute(g_query)
                guidelines = list(g_res.scalars().all())
            except Exception:
                guidelines = []

        # 3. Resolve Approved Facts
        facts: list[ApprovedFact] = []
        if session is not None:
            try:
                f_query = select(ApprovedFact).where(
                    ApprovedFact.workspace_id == workspace_id,
                    ApprovedFact.is_active == True,  # noqa: E712
                )
                f_res = await session.execute(f_query)
                facts = list(f_res.scalars().all())
            except Exception:
                facts = []

        if not facts:
            facts = cls.create_default_benchmark_facts(workspace_id)

        # 4. Execute Analysis Pipeline across all 15 samples
        sample_results: list[EvaluationSampleResult] = []
        latencies_ms: list[float] = []

        total_tp = 0
        total_fp = 0
        total_fn = 0

        for sample in BENCHMARK_TESTSET:
            t0 = time.perf_counter()

            # Execute Stage 1: Deterministic Engine
            deterministic_hits = DeterministicRuleEngine.analyze_document(
                content_text=sample.text,
                brand_profile=profile,
                guidelines=guidelines,
            )

            # Execute Stage 2: Temporal Fact Engine
            temporal_hits = await TemporalFactEngine.evaluate_claims(
                content_text=sample.text,
                workspace_id=workspace_id,
                session=session,
                preloaded_facts=facts,
            )

            # Execute Stage 3: Privacy Gate / Tone Evaluation
            tone_hits = await PrivacyGateRouter.analyze_tone_and_messaging(
                content_text=sample.text,
                brand_profile=profile,
                workspace_id=workspace_id,
                session=session,
            )

            latency = round((time.perf_counter() - t0) * 1000, 2)
            latencies_ms.append(latency)

            # Collect detected categories
            detected_cats: list[str] = []
            for d in deterministic_hits:
                cat_val = d.issue_category.value if hasattr(d.issue_category, "value") else str(d.issue_category)
                detected_cats.append(cat_val)
            for t in temporal_hits:
                cat_val = t.issue_category.value if hasattr(t.issue_category, "value") else str(t.issue_category)
                detected_cats.append(cat_val)
            for tone in tone_hits:
                detected_cats.append("TONE")

            # Multi-label category evaluation per sample
            def _normalize_cat(c: str) -> str:
                return "UNSUPPORTED_CLAIM" if c in ("UNSUBSTANTIATED_CLAIM", "UNSUPPORTED_CLAIM") else c

            gt_set = {_normalize_cat(c) for c in sample.ground_truth_categories}
            det_set = {_normalize_cat(c) for c in detected_cats}

            tp_set = gt_set.intersection(det_set)
            fp_set = det_set.difference(gt_set)
            fn_set = gt_set.difference(det_set)

            sample_tp = len(tp_set)
            sample_fp = len(fp_set)
            sample_fn = len(fn_set)

            total_tp += sample_tp
            total_fp += sample_fp
            total_fn += sample_fn

            # Determine sample classification status
            if len(gt_set) == 0 and len(det_set) == 0:
                status = "CLEAN_PASS"
            elif sample_fn == 0 and sample_fp == 0:
                status = "PERFECT_MATCH"
            else:
                status = "PARTIAL_MATCH"

            sample_results.append(
                EvaluationSampleResult(
                    sample_id=sample.sample_id,
                    title=sample.title,
                    text=sample.text,
                    ground_truth_categories=sample.ground_truth_categories,
                    detected_categories=detected_cats,
                    detected_findings_count=len(detected_cats),
                    true_positives=sample_tp,
                    false_positives=sample_fp,
                    false_negatives=sample_fn,
                    latency_ms=latency,
                    status=status,
                )
            )

        # 5. Compute Aggregate Macro Metrics
        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
        f1_score = (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        p95_latency = float(np.percentile(latencies_ms, 95)) if latencies_ms else 0.0
        avg_latency = float(np.mean(latencies_ms)) if latencies_ms else 0.0
        min_latency = float(np.min(latencies_ms)) if latencies_ms else 0.0
        max_latency = float(np.max(latencies_ms)) if latencies_ms else 0.0

        return EvaluationBenchmarkResponse(
            total_samples=len(BENCHMARK_TESTSET),
            true_positives=total_tp,
            false_positives=total_fp,
            false_negatives=total_fn,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1_score=round(f1_score, 4),
            p95_latency_ms=round(p95_latency, 2),
            avg_latency_ms=round(avg_latency, 2),
            min_latency_ms=round(min_latency, 2),
            max_latency_ms=round(max_latency, 2),
            samples=sample_results,
            evaluated_at=evaluated_at,
        )
