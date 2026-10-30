"""
BrandShield AI - Stage 2 Temporal Fact & Hybrid RAG Retrieval Engine.
Extracts quantitative, comparative, and temporal assertions from the document AST,
queries approved_facts via Reciprocal Rank Fusion (RRF: pgvector + ts_rank_cd),
and enforces strict Temporal Fact Governance:
- Expired facts -> STALE_FACT_REVERIFY
- Numerical / factual contradictions -> FLAGGED_HIGH_CONFIDENCE
- Ungrounded claims without approved facts -> NEEDS_VERIFICATION_MISSING_EVIDENCE (evidence-linked)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import inspect
import re
from typing import Any, Optional
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import DetectorSource, FindingCategory, SeverityLevel, TriageStatus
from app.infrastructure.db.models import ApprovedFact, BrandGuideline

settings = get_settings()

# Quantitative claim patterns: percentages, multipliers, currency, large quantities
QUANTITATIVE_PATTERN = re.compile(
    r"(?:\$|€|£)?\b\d+(?:[\.,]\d+)?\s*(?:%|percent|x|fold|million|billion|trillion|k|m|b|users|customers|clients|uptime|sla|ms|seconds)?\b",
    re.IGNORECASE,
)

# Superlative and absolute marketing assertions
SUPERLATIVE_PATTERN = re.compile(
    r"(?:#\d+|\b(?:guaranteed|unmatched|industry-leading|fastest|most secure|100%|zero downtime|flawless|infallible|proven leader)\b)",
    re.IGNORECASE,
)

# Temporal claim markers
TEMPORAL_PATTERN = re.compile(
    r"\b(?:as of|since|in the last|past|over the past|during)\s+(?:\d{4}|Q[1-4]|\d+\s*(?:months|years|quarters))\b",
    re.IGNORECASE,
)


@dataclass
class ExtractedClaim:
    """Quantitative or superlative claim identified within the document text."""
    claim_text: str
    start_offset: int
    end_offset: int
    claim_type: str  # "QUANTITATIVE", "SUPERLATIVE", "TEMPORAL"
    extracted_metrics: list[str] = field(default_factory=list)


@dataclass
class TemporalFactFinding:
    """Finding produced by the temporal fact governance engine."""
    issue_category: FindingCategory
    severity: SeverityLevel
    confidence_score: float
    triage_status: TriageStatus
    start_offset: int
    end_offset: int
    explanation_reason: str
    suggested_correction: Optional[str] = None
    detector_source: DetectorSource = DetectorSource.TEMPORAL_FACT_MATCHER
    linked_fact_id: Optional[uuid.UUID] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TemporalFactEngine:
    """
    Stage 2 Engine:
    Executes claim extraction, Reciprocal Rank Fusion (RRF) hybrid retrieval,
    and temporal validity enforcement against the ground-truth repository.
    """

    @classmethod
    def extract_claims(cls, content_text: str) -> list[ExtractedClaim]:
        """
        Parses sentences across document text and isolates factual assertions.
        """
        claims: list[ExtractedClaim] = []
        sentence_pattern = re.compile(r"((?:[^\.\?!]|\.(?=\d))+[\.\?!]*(?:\s+|$))")

        for match in sentence_pattern.finditer(content_text):
            raw_sentence = match.group(0)
            clean_sentence = raw_sentence.strip()
            if not clean_sentence or len(clean_sentence) < 8:
                continue

            rel_offset = raw_sentence.find(clean_sentence)
            s_start = match.start() + rel_offset
            s_end = s_start + len(clean_sentence)

            # Check for quantitative claims
            quant_matches = [m.group(0) for m in QUANTITATIVE_PATTERN.finditer(clean_sentence) if re.search(r"\d", m.group(0))]
            super_matches = [m.group(0) for m in SUPERLATIVE_PATTERN.finditer(clean_sentence)]
            temp_matches = [m.group(0) for m in TEMPORAL_PATTERN.finditer(clean_sentence)]

            if super_matches:
                claims.append(
                    ExtractedClaim(
                        claim_text=clean_sentence,
                        start_offset=s_start,
                        end_offset=s_end,
                        claim_type="SUPERLATIVE",
                        extracted_metrics=super_matches,
                    )
                )
            elif quant_matches:
                claims.append(
                    ExtractedClaim(
                        claim_text=clean_sentence,
                        start_offset=s_start,
                        end_offset=s_end,
                        claim_type="QUANTITATIVE",
                        extracted_metrics=quant_matches,
                    )
                )
            elif temp_matches:
                claims.append(
                    ExtractedClaim(
                        claim_text=clean_sentence,
                        start_offset=s_start,
                        end_offset=s_end,
                        claim_type="TEMPORAL",
                        extracted_metrics=temp_matches,
                    )
                )

        return claims

    @classmethod
    def compute_rrf_score(
        cls,
        dense_rank: Optional[int],
        sparse_rank: Optional[int],
        k: int = 60,
    ) -> float:
        """
        Computes Reciprocal Rank Fusion (RRF) score:
        RRF = sum(1 / (k + rank_m)) for available ranking models.
        """
        score = 0.0
        if dense_rank is not None and dense_rank > 0:
            score += 1.0 / (k + dense_rank)
        if sparse_rank is not None and sparse_rank > 0:
            score += 1.0 / (k + sparse_rank)
        return score

    @classmethod
    async def query_hybrid_rrf_facts(
        cls,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        query_text: str,
        query_embedding: Optional[list[float]] = None,
        top_k: int = 10,
        rrf_k: int = 60,
    ) -> list[tuple[ApprovedFact, float]]:
        """
        Executes Reciprocal Rank Fusion (RRF) combining PostgreSQL ts_rank_cd full-text search
        and pgvector cosine distance on approved_facts.
        RRF = sum(1 / (k + rank)) across available retrieval models.
        """
        try:
            ranks: dict[uuid.UUID, dict[str, int]] = {}
            fact_by_id: dict[uuid.UUID, ApprovedFact] = {}

            # 1. Lexical full-text search using ts_rank_cd
            sparse_query = (
                select(
                    ApprovedFact,
                    func.ts_rank_cd(
                        func.to_tsvector("english", ApprovedFact.fact_statement),
                        func.plainto_tsquery("english", query_text),
                    ).label("sparse_score"),
                )
                .where(
                    ApprovedFact.workspace_id == workspace_id,
                    ApprovedFact.is_active == True,  # noqa: E712
                )
                .order_by(text("sparse_score DESC"))
                .limit(top_k * 2)
            )
            sparse_res = await session.execute(sparse_query)
            for idx, (fact, _) in enumerate(sparse_res.all(), start=1):
                fact_by_id[fact.id] = fact
                ranks.setdefault(fact.id, {})["sparse"] = idx

            # 2. Dense vector similarity using pgvector cosine distance
            if query_embedding:
                dense_query = (
                    select(
                        ApprovedFact,
                        ApprovedFact.embedding.cosine_distance(query_embedding).label("distance"),
                    )
                    .where(
                        ApprovedFact.workspace_id == workspace_id,
                        ApprovedFact.is_active == True,  # noqa: E712
                    )
                    .order_by(text("distance ASC"))
                    .limit(top_k * 2)
                )
                dense_res = await session.execute(dense_query)
                for idx, (fact, _) in enumerate(dense_res.all(), start=1):
                    fact_by_id[fact.id] = fact
                    ranks.setdefault(fact.id, {})["dense"] = idx

            scored_facts: list[tuple[ApprovedFact, float]] = []
            for fact_id, rank_dict in ranks.items():
                s_rank = rank_dict.get("sparse")
                d_rank = rank_dict.get("dense")
                rrf_score = cls.compute_rrf_score(dense_rank=d_rank, sparse_rank=s_rank, k=rrf_k)
                scored_facts.append((fact_by_id[fact_id], rrf_score))

            scored_facts.sort(key=lambda x: x[1], reverse=True)
            return scored_facts[:top_k]

        except Exception:
            # Fallback for SQLite / unit testing without pgvector & ts_rank_cd
            query = select(ApprovedFact).where(
                ApprovedFact.workspace_id == workspace_id,
                ApprovedFact.is_active == True,  # noqa: E712
            )
            res = await session.execute(query)
            facts = list(res.scalars().all())
            scored = [
                (f, cls.calculate_text_similarity(query_text, f.fact_statement))
                for f in facts
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_k]

    @classmethod
    async def query_hybrid_rrf_guidelines(
        cls,
        session: AsyncSession,
        brand_profile_id: uuid.UUID,
        query_text: str,
        query_embedding: Optional[list[float]] = None,
        top_k: int = 10,
        rrf_k: int = 60,
    ) -> list[tuple[BrandGuideline, float]]:
        """
        Executes Reciprocal Rank Fusion (RRF) combining PostgreSQL ts_rank_cd full-text search
        and pgvector cosine distance on brand_guidelines.
        """
        try:
            ranks: dict[uuid.UUID, dict[str, int]] = {}
            guideline_by_id: dict[uuid.UUID, BrandGuideline] = {}

            sparse_query = (
                select(
                    BrandGuideline,
                    func.ts_rank_cd(
                        BrandGuideline.search_vector,
                        func.plainto_tsquery("english", query_text),
                    ).label("sparse_score"),
                )
                .where(
                    BrandGuideline.brand_profile_id == brand_profile_id,
                    BrandGuideline.is_active == True,  # noqa: E712
                )
                .order_by(text("sparse_score DESC"))
                .limit(top_k * 2)
            )
            sparse_res = await session.execute(sparse_query)
            for idx, (guideline, _) in enumerate(sparse_res.all(), start=1):
                guideline_by_id[guideline.id] = guideline
                ranks.setdefault(guideline.id, {})["sparse"] = idx

            if query_embedding:
                dense_query = (
                    select(
                        BrandGuideline,
                        BrandGuideline.embedding.cosine_distance(query_embedding).label("distance"),
                    )
                    .where(
                        BrandGuideline.brand_profile_id == brand_profile_id,
                        BrandGuideline.is_active == True,  # noqa: E712
                    )
                    .order_by(text("distance ASC"))
                    .limit(top_k * 2)
                )
                dense_res = await session.execute(dense_query)
                for idx, (guideline, _) in enumerate(dense_res.all(), start=1):
                    guideline_by_id[guideline.id] = guideline
                    ranks.setdefault(guideline.id, {})["dense"] = idx

            scored_guidelines: list[tuple[BrandGuideline, float]] = []
            for g_id, rank_dict in ranks.items():
                s_rank = rank_dict.get("sparse")
                d_rank = rank_dict.get("dense")
                rrf_score = cls.compute_rrf_score(dense_rank=d_rank, sparse_rank=s_rank, k=rrf_k)
                scored_guidelines.append((guideline_by_id[g_id], rrf_score))

            scored_guidelines.sort(key=lambda x: x[1], reverse=True)
            return scored_guidelines[:top_k]

        except Exception:
            query = select(BrandGuideline).where(
                BrandGuideline.brand_profile_id == brand_profile_id,
                BrandGuideline.is_active == True,  # noqa: E712
            )
            res = await session.execute(query)
            guidelines = list(res.scalars().all())
            scored = [
                (g, cls.calculate_text_similarity(query_text, g.clause_text))
                for g in guidelines
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_k]

    @classmethod
    def calculate_text_similarity(cls, text_a: str, text_b: str) -> float:
        """
        Computes token-level Jaccard and containment similarity [0.0, 1.0].
        Provides robust in-memory semantic grounding matching.
        """
        tokens_a = set(re.findall(r"\w+", text_a.lower()))
        tokens_b = set(re.findall(r"\w+", text_b.lower()))

        if not tokens_a or not tokens_b:
            return 0.0

        intersection = tokens_a.intersection(tokens_b)
        union = tokens_a.union(tokens_b)
        jaccard = len(intersection) / len(union)

        # Containment boost if a substantial phrase from B appears in A
        containment = len(intersection) / min(len(tokens_a), len(tokens_b))
        return 0.4 * jaccard + 0.6 * containment

    @classmethod
    async def evaluate_claims(
        cls,
        content_text: str,
        workspace_id: uuid.UUID,
        session: Optional[AsyncSession] = None,
        preloaded_facts: Optional[list[ApprovedFact]] = None,
    ) -> list[TemporalFactFinding]:
        """
        Extracts claims, resolves approved ground-truth facts via RRF and similarity,
        and generates triaged findings with temporal staleness and missing evidence guards.
        """
        findings: list[TemporalFactFinding] = []
        claims = cls.extract_claims(content_text)

        # Retrieve candidate approved facts for workspace
        facts: list[ApprovedFact] = []
        if preloaded_facts is not None:
            facts = preloaded_facts
        elif session is not None:
            try:
                query = select(ApprovedFact).where(
                    ApprovedFact.workspace_id == workspace_id,
                    ApprovedFact.is_active == True,  # noqa: E712
                )
                result = await session.execute(query)
                scalars = result.scalars()
                if hasattr(scalars, "all"):
                    res_all = scalars.all()
                    if inspect.isawaitable(res_all):
                        res_all = await res_all
                    facts = list(res_all)
            except Exception:
                facts = []

        now = datetime.now(timezone.utc)
        review_period_days = 90
        if session is not None:
            try:
                from app.infrastructure.db.models import Workspace
                ws = await session.get(Workspace, workspace_id)
                if ws and hasattr(ws, "review_rules") and isinstance(ws.review_rules, dict):
                    review_period_days = int(ws.review_rules.get("fact_review_period_days", 90))
            except Exception:
                pass

        for claim in claims:
            best_fact: Optional[ApprovedFact] = None
            best_similarity: float = 0.0

            # Compute semantic and lexical similarity against approved repository
            for fact in facts:
                sim = cls.calculate_text_similarity(claim.claim_text, fact.fact_statement)
                if sim > best_similarity:
                    best_similarity = sim
                    best_fact = fact

            # Similarity threshold for claim alignment
            SIMILARITY_THRESHOLD = 0.35

            if best_fact is not None and best_similarity >= SIMILARITY_THRESHOLD:
                # --------------------------------------------------------------
                # Condition A: Expired Fact -> STALE_FACT_REVERIFY
                # --------------------------------------------------------------
                is_expired = bool(getattr(best_fact, "expiry_date", None) and best_fact.expiry_date < now)
                is_stale_window = False
                fact_timestamp = getattr(best_fact, "updated_at", None) or getattr(best_fact, "created_at", None)
                if isinstance(fact_timestamp, datetime):
                    from datetime import timedelta
                    if fact_timestamp + timedelta(days=review_period_days) < now:
                        is_stale_window = True

                if is_expired or is_stale_window:
                    staleness_msg = (
                        f"Temporal staleness alert: Factual assertion aligns with approved claim "
                        f"'{best_fact.fact_statement[:80]}...', but substantiation expired on "
                        f"{best_fact.expiry_date.strftime('%Y-%m-%d')}."
                        if is_expired else
                        f"Temporal staleness alert: Factual assertion aligns with approved claim "
                        f"'{best_fact.fact_statement[:80]}...', but fact review period ({review_period_days} days) has elapsed."
                    )
                    findings.append(
                        TemporalFactFinding(
                            issue_category=FindingCategory.STALE_FACT,
                            severity=SeverityLevel.HIGH,
                            confidence_score=0.95,
                            triage_status=TriageStatus.STALE_FACT_REVERIFY,
                            start_offset=claim.start_offset,
                            end_offset=claim.end_offset,
                            explanation_reason=f"{staleness_msg} Responsible Owner (User ID: {best_fact.responsible_owner_id}) must recertify.",
                            suggested_correction=f"Recertify fact substantiation via verified source: {best_fact.original_source_url}",
                            detector_source=DetectorSource.TEMPORAL_FACT_MATCHER,
                            linked_fact_id=best_fact.id,
                            metadata={
                                "expiry_date": best_fact.expiry_date.isoformat(),
                                "responsible_owner_id": str(best_fact.responsible_owner_id),
                                "source_url": best_fact.original_source_url,
                                "review_period_days": review_period_days,
                            },
                        )
                    )

                else:
                    # ----------------------------------------------------------
                    # Condition B: Contradiction with Valid Approved Fact
                    # ----------------------------------------------------------
                    claim_numbers = set(re.findall(r"\b\d+(?:[\.,]\d+)?%?\b", claim.claim_text))
                    fact_numbers = set(re.findall(r"\b\d+(?:[\.,]\d+)?%?\b", best_fact.fact_statement))

                    # If both contain numbers but numbers diverge -> Contradiction
                    is_contradiction = bool(claim_numbers and fact_numbers and not (claim_numbers & fact_numbers))

                    if is_contradiction:
                        findings.append(
                            TemporalFactFinding(
                                issue_category=FindingCategory.UNSUBSTANTIATED_CLAIM,
                                severity=SeverityLevel.HIGH,
                                confidence_score=0.92,
                                triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
                                start_offset=claim.start_offset,
                                end_offset=claim.end_offset,
                                explanation_reason=(
                                    f"Numerical contradiction: Document asserts metrics {list(claim_numbers)} "
                                    f"which conflict with certified corporate ground truth: '{best_fact.fact_statement}'. "
                                    f"Primary evidence source: {best_fact.original_source_url}"
                                ),
                                suggested_correction=best_fact.fact_statement,
                                detector_source=DetectorSource.TEMPORAL_FACT_MATCHER,
                                linked_fact_id=best_fact.id,
                                metadata={"original_source_url": best_fact.original_source_url},
                            )
                        )

            else:
                # --------------------------------------------------------------
                # Condition C: Factual Claim with NO Approved Grounding Fact
                # Evidence-Linked Safe Harbor: NEVER claim confirmed breach!
                # --------------------------------------------------------------
                findings.append(
                    TemporalFactFinding(
                        issue_category=FindingCategory.UNSUBSTANTIATED_CLAIM,
                        severity=SeverityLevel.MEDIUM,
                        confidence_score=0.70,
                        triage_status=TriageStatus.NEEDS_VERIFICATION_MISSING_EVIDENCE,
                        start_offset=claim.start_offset,
                        end_offset=claim.end_offset,
                        explanation_reason="Supporting evidence unavailable in approved fact repository; needs verification.",
                        suggested_correction=None,
                        detector_source=DetectorSource.TEMPORAL_FACT_MATCHER,
                        linked_fact_id=None,
                        metadata={"claim_type": claim.claim_type, "metrics": claim.extracted_metrics},
                    )
                )

        return findings
