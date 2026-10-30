"""
BrandShield AI - AI Teammate Strategy Plugin Template.
================================================================================
ATTENTION AI ROLE TEAMMATE:
Drop your custom prompt chains, vector retrieval weights, and expanded labelled
test cases into this file! You do NOT need to touch FastAPI routers, Pydantic schemas,
or SQLAlchemy async session internals. Everything here integrates automatically via
the AIPluginRegistry port.
================================================================================
"""

import re
import time
from typing import Any, Optional

from app.domain.ai_plugin_port import (
    AIPluginRegistry,
    BaseAIAnalyzerPlugin,
    BaseVectorRetrieverPlugin,
    PluginClaimContext,
    PluginClaimFinding,
    PluginDocumentContext,
    PluginRetrievalQuery,
    PluginRetrievedDocument,
    PluginToneAnalysisResult,
    PluginToneFinding,
)

# ===============================================================================
# SECTION 1: CUSTOM PROMPT CHAINS & SYSTEM DIRECTIVES
# ===============================================================================

SYSTEM_COMPLIANCE_DIRECTIVE = """
You are the BrandShield Enterprise Compliance LLM.
Your task is to analyze document passages for brand safety, legal truth-in-advertising,
and tone violations.

Brand Parameters:
- Formality Ceiling: {target_formality}/10
- Voice Tone: {tone_voice}
- Prohibited Terminology: {prohibited_terms}

Output Strict JSON containing:
- category: "TONE" | "TERMINOLOGY" | "MESSAGING"
- severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
- confidence: float (0.0 to 1.0)
- explanation: Detailed rationale
- suggested_rewrite: Context-preserving replacement
"""

FEW_SHOT_DEMONSTRATIONS = [
    {
        "input": "Our product is 100% risk-free with unbeatable performance.",
        "output": {
            "category": "TERMINOLOGY",
            "severity": "CRITICAL",
            "confidence": 0.99,
            "explanation": "Absolute superlatives ('100% risk-free', 'unbeatable') violate SEC and FTC truth-in-advertising guidelines.",
            "suggested_rewrite": "Our product is engineered for managed risk with competitive performance.",
        },
    },
    {
        "input": "We are crazy excited about our insane new features.",
        "output": {
            "category": "TONE",
            "severity": "MEDIUM",
            "confidence": 0.88,
            "explanation": "Colloquial slang ('crazy excited', 'insane') departs from executive B2B tone standards.",
            "suggested_rewrite": "We are proud to introduce our enhanced platform capabilities.",
        },
    },
]

# ===============================================================================
# SECTION 2: CUSTOM AI ANALYZER STRATEGY
# ===============================================================================

class TeammateAIAnalyzerPlugin(BaseAIAnalyzerPlugin):
    """AI Teammate plug‑in strategy.
    Modify this class to plug in OpenAI, Anthropic, HuggingFace, or custom local models.
    """

    @property
    def plugin_name(self) -> str:
        return "teammate-enterprise-analyzer"

    @property
    def plugin_version(self) -> str:
        return "1.0.0"

    async def analyze_tone(self, context: PluginDocumentContext) -> PluginToneAnalysisResult:
        """Executes tone and brand consistency analysis.
        Drop your prompt invocation logic or API router here.
        """
        t0 = time.perf_counter()
        findings: list[PluginToneFinding] = []
        text = context.content_text

        # 1. Terminology scanning using custom parameters
        for term in context.prohibited_terms:
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for m in pattern.finditer(text):
                findings.append(
                    PluginToneFinding(
                        issue_category="TERMINOLOGY",
                        severity="CRITICAL" if "risk-free" in term.lower() or "guarantee" in term.lower() else "HIGH",
                        confidence_score=0.98,
                        start_offset=m.start(),
                        end_offset=m.end(),
                        flagged_text=m.group(0),
                        explanation_reason=f"Term '{m.group(0)}' breaches approved brand matrix.",
                        suggested_correction=None,
                        rule_reference="CUSTOM_PROMPT_CHAIN",
                    )
                )

        # 2. Executive Formality Scoring
        words = text.split()
        avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
        formality_score = min(10.0, max(1.0, (avg_word_len * 1.5)))

        elapsed_ms = (time.perf_counter() - t0) * 1000
        return PluginToneAnalysisResult(
            findings=findings,
            formality_score=round(formality_score, 2),
            sentiment_score=0.75,
            processing_duration_ms=round(elapsed_ms, 2),
            plugin_identifier=f"{self.plugin_name}:{self.plugin_version}",
        )

    async def verify_claims(self, context: PluginClaimContext) -> list[PluginClaimFinding]:
        """Verify factual claims against approved facts.
        Simple token overlap matching is used for demonstration.
        Returns a list of PluginClaimFinding objects.
        """
        results: list[PluginClaimFinding] = []
        for claim in context.claims_to_verify:
            claim_lower = claim.lower()
            matched_fact = None
            for fact in context.approved_facts:
                stmt = fact.get("statement", "").lower()
                if any(token in stmt for token in claim_lower.split() if len(token) > 3):
                    matched_fact = fact
                    break
            if matched_fact:
                results.append(
                    PluginClaimFinding(
                        claim_text=claim,
                        verification_status="VERIFIED",
                        confidence=0.94,
                        supporting_fact_id=matched_fact.get("id"),
                        citation_snippet=matched_fact.get("statement"),
                        explanation="Claim matched approved fact.",
                    )
                )
            else:
                results.append(
                    PluginClaimFinding(
                        claim_text=claim,
                        verification_status="NEEDS_VERIFICATION",
                        confidence=0.70,
                        supporting_fact_id=None,
                        citation_snippet=None,
                        explanation="No matching approved fact found.",
                    )
                )
        return results

# ===============================================================================
# SECTION 3: CUSTOM RETRIEVAL STRATEGY (DENSE + SPARSE WEIGHTS)
# ===============================================================================

class TeammateVectorRetrieverPlugin(BaseVectorRetrieverPlugin):
    """Configurable hybrid retrieval algorithm.
    Tune dense alpha vs sparse beta weights or Reciprocal Rank Fusion parameters.
    """

    def __init__(self, dense_weight: float = 0.65, sparse_weight: float = 0.35, rrf_k: int = 60) -> None:
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.rrf_k = rrf_k

    async def embed_query(self, text: str) -> list[float]:
        """Generate a dummy embedding vector for a query string."""
        return [0.0] * 768

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate dummy embeddings for a list of documents."""
        return [[0.0] * 768 for _ in texts]

    async def retrieve_relevant_guidelines(self, query, corpus) -> list[PluginRetrievedDocument]:
        """Placeholder retrieval for guidelines – returns empty list."""
        return []

    async def retrieve_relevant_facts(self, query, corpus) -> list[PluginRetrievedDocument]:
        """Placeholder retrieval for facts – returns empty list."""
        return []

    @property
    def retriever_name(self) -> str:
        return "teammate-hybrid-rrf-retriever"

    async def rank_candidates(self, query: PluginRetrievalQuery) -> list[PluginRetrievedDocument]:
        """Calculate hybrid score = (alpha * dense_cosine) + (beta * sparse_bm25)."""
        ranked: list[PluginRetrievedDocument] = []
        q_tokens = set(re.findall(r"\w+", query.query_text.lower()))
        for doc in query.candidate_pool:
            doc_tokens = set(re.findall(r"\w+", doc.text.lower()))
            overlap = len(q_tokens & doc_tokens) / max(len(q_tokens), 1)
            dense_sim = 0.85 if overlap > 0.3 else 0.40
            fused_score = (self.dense_weight * dense_sim) + (self.sparse_weight * overlap)
            ranked.append(
                PluginRetrievedDocument(
                    document_id=doc.id,
                    content=doc.text,
                    score=round(fused_score, 4),
                    metadata={**doc.metadata, "hybrid_algorithm": "tuned_rrf_linear_blend"},
                )
            )
        ranked.sort(key=lambda x: x.score, reverse=True)
        return ranked[: query.top_k]

# ===============================================================================
# SECTION 4: EXPANDED LABELLED BENCHMARK TEST CASES
# ===============================================================================

EXPANDED_BENCHMARK_SAMPLES = [
    {
        "sample_id": "EXPANDED-01",
        "title": "Unsubstantiated Competitor Comparison",
        "text": "Acme FinTech processes settlement 10x faster than all competitor banking networks combined.",
        "ground_truth_categories": ["UNSUBSTANTIATED_CLAIM", "TERMINOLOGY"],
    },
    {
        "sample_id": "EXPANDED-02",
        "title": "Compliant Multi-Currency Disclosure",
        "text": "Acme FinTech™ supports multi-currency settlement in USD, EUR, and GBP for verified enterprise accounts.",
        "ground_truth_categories": [],  # Clean passage (True Negative)
    },
]

# ===============================================================================
# SECTION 5: PLUGIN REGISTRATION HELPER
# ===============================================================================

def register_teammate_ai_plugins() -> None:
    """Registers your custom AI plugin components into the BrandShield AI engine."""
    AIPluginRegistry.register_analyzer(TeammateAIAnalyzerPlugin())
    AIPluginRegistry.register_retriever(TeammateVectorRetrieverPlugin())

# Auto‑register on import
register_teammate_ai_plugins()
