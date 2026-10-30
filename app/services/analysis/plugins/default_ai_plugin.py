"""
BrandShield AI - Reference AI Teammate Plugin Implementation.
Demonstrates how AI team members can drop their prompt templates, claim verification logic,
and vector retrieval algorithms into this directory with zero database or router dependencies.
"""

import math
import re
import time
from typing import Any

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


class DefaultAIAnalyzerPlugin(BaseAIAnalyzerPlugin):
    """
    Reference Analyzer Strategy for the AI engineering teammate.
    Drop custom prompt templates, LLM client calls, or heuristic fine-tunes here.
    """

    PROMPT_TEMPLATE = """
    You are an enterprise brand compliance guardian for {brand_name}.
    Voice Guideline: {tone_voice}
    Prohibited Terms: {prohibited_terms}

    Evaluate the following document:
    \"\"\"{content_text}\"\"\"
    """

    @property
    def plugin_name(self) -> str:
        return "default-heuristic-analyzer"

    @property
    def plugin_version(self) -> str:
        return "1.0.0"

    async def analyze_tone(self, context: PluginDocumentContext) -> PluginToneAnalysisResult:
        """
        Executes tone and prohibited claim analysis against the document context.
        """
        t0 = time.perf_counter()
        findings: list[PluginToneFinding] = []
        text = context.content_text

        # 1. Prohibited term scanner
        for term in context.prohibited_terms:
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for m in pattern.finditer(text):
                findings.append(
                    PluginToneFinding(
                        issue_category="PROHIBITED_CLAIM",
                        severity="CRITICAL",
                        confidence_score=0.98,
                        start_offset=m.start(),
                        end_offset=m.end(),
                        flagged_text=m.group(),
                        explanation_reason=f"Term '{term}' is explicitly prohibited by brand policy.",
                        suggested_correction=None,
                        rule_reference="BRAND_TERM_BLACKLIST",
                    )
                )

        # 2. Aggressive tone triggers (example demo heuristic)
        aggressive_words = ["guaranteed", "miracle", "100% cure", "risk-free"]
        for word in aggressive_words:
            pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
            for m in pattern.finditer(text):
                findings.append(
                    PluginToneFinding(
                        issue_category="TONE",
                        severity="HIGH",
                        confidence_score=0.92,
                        start_offset=m.start(),
                        end_offset=m.end(),
                        flagged_text=m.group(),
                        explanation_reason=f"Hyperbolic phrasing '{word}' violates substantiated tone requirements.",
                        suggested_correction="clinically proven" if "cure" in word else "substantiated",
                        rule_reference="TONE_SUBSTANTIATION",
                    )
                )

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return PluginToneAnalysisResult(
            findings=findings,
            model_name=self.plugin_name,
            prompt_tokens_used=len(text.split()) * 2,
            completion_tokens_used=len(findings) * 20,
            latency_ms=latency_ms,
            summary_notes=f"Analyzed {len(text)} characters; flagged {len(findings)} issues.",
        )

    async def verify_claims(self, context: PluginClaimContext) -> list[PluginClaimFinding]:
        """
        Verifies extracted factual assertions against approved facts.
        Ungrounded assertions are strictly marked 'NEEDS_VERIFICATION'.
        """
        results: list[PluginClaimFinding] = []
        for claim in context.claims_to_verify:
            matched_fact = None
            for fact in context.approved_facts:
                fact_stmt = fact.get("statement", "")
                # Simple word-overlap grounding demo
                claim_words = set(claim.lower().split())
                fact_words = set(fact_stmt.lower().split())
                overlap = len(claim_words.intersection(fact_words))
                if overlap >= 3:
                    matched_fact = fact
                    break

            if matched_fact:
                results.append(
                    PluginClaimFinding(
                        claim_text=claim,
                        verification_status="VERIFIED",
                        confidence=0.95,
                        supporting_fact_id=str(matched_fact.get("id")),
                        citation_snippet=matched_fact.get("statement"),
                        explanation="Claim is substantiated by approved organization fact.",
                    )
                )
            else:
                results.append(
                    PluginClaimFinding(
                        claim_text=claim,
                        verification_status="NEEDS_VERIFICATION",
                        confidence=0.50,
                        supporting_fact_id=None,
                        citation_snippet=None,
                        explanation="No verified organizational fact substantiates this claim. Grounding required.",
                    )
                )
        return results


class DefaultVectorRetrieverPlugin(BaseVectorRetrieverPlugin):
    """
    Reference Vector Retriever Plugin for embedding search and RAG experiments.
    """

    @property
    def retriever_name(self) -> str:
        return "default-hash-retriever"

    async def embed_query(self, text: str) -> list[float]:
        """Deterministic 8-dimensional mock embedding for demonstration."""
        val = sum(ord(c) for c in text)
        return [math.sin(val + i) for i in range(8)]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_query(t) for t in texts]

    async def retrieve_relevant_guidelines(
        self,
        query: PluginRetrievalQuery,
        corpus: list[PluginRetrievedDocument],
    ) -> list[PluginRetrievedDocument]:
        """Simple keyword / token overlap ranking."""
        q_tokens = set(query.query_text.lower().split())
        scored: list[PluginRetrievedDocument] = []
        for doc in corpus:
            doc_tokens = set(doc.content.lower().split())
            overlap = len(q_tokens.intersection(doc_tokens))
            score = min(1.0, overlap / max(1, len(q_tokens)))
            if score >= query.similarity_threshold:
                scored.append(
                    PluginRetrievedDocument(
                        document_id=doc.document_id,
                        content=doc.content,
                        score=score,
                        metadata=doc.metadata,
                    )
                )
        scored.sort(key=lambda d: d.score, reverse=True)
        return scored[: query.top_k]

    async def retrieve_relevant_facts(
        self,
        query: PluginRetrievalQuery,
        corpus: list[PluginRetrievedDocument],
    ) -> list[PluginRetrievedDocument]:
        return await self.retrieve_relevant_guidelines(query, corpus)


# Automatically register reference plugins
AIPluginRegistry.register_analyzer(DefaultAIAnalyzerPlugin())
AIPluginRegistry.register_retriever(DefaultVectorRetrieverPlugin())
