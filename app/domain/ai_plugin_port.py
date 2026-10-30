"""
BrandShield AI - AI Teammate Plug-in Port.
Isolated Strategy Interfaces and strict Pydantic v2 domain schemas for AI/ML engineering.

Allows AI engineers and data scientists to drop custom prompt templates,
fine-tuned models, embedding algorithms, or evaluation benchmark test sets into:
    `app/services/analysis/plugins/`
WITHOUT touching database sessions, RBAC security guards, or FastAPI routing.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# 1. Pydantic v2 Contracts for AI Analyzer Plugins
# ==============================================================================

class PluginDocumentContext(BaseModel):
    """
    Clean, decoupled document and brand payload supplied to an AI Analyzer Plugin.
    Free of ORM entities, session references, or HTTP request objects.
    """
    content_text: str = Field(..., min_length=1, description="Raw document text to analyze")
    brand_name: str = Field(..., description="Enterprise client brand name")
    brand_tone_voice: Optional[str] = Field(None, description="Target brand voice guideline (e.g. 'Empathetic, Clinical')")
    prohibited_terms: list[str] = Field(default_factory=list, description="Explicit blacklist of prohibited terms")
    guidelines: list[dict[str, Any]] = Field(default_factory=list, description="Active brand compliance guidelines")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary campaign or channel metadata")

    model_config = ConfigDict(frozen=True)


class PluginToneFinding(BaseModel):
    """Normalized compliance or tone finding produced by an AI plugin."""
    issue_category: str = Field(..., description="E.g. 'TONE', 'MESSAGING', 'PROHIBITED_CLAIM'")
    severity: str = Field(..., description="'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Calibrated confidence [0.0, 1.0]")
    start_offset: int = Field(..., ge=0, description="Start character offset in content_text")
    end_offset: int = Field(..., ge=0, description="End character offset in content_text")
    flagged_text: str = Field(..., description="Snippet of text causing the detection")
    explanation_reason: str = Field(..., description="Actionable reason explaining why this violates policy")
    suggested_correction: Optional[str] = Field(None, description="Suggested compliant replacement")
    rule_reference: Optional[str] = Field(None, description="Optional rule or policy identifier")

    model_config = ConfigDict(frozen=True)

    @property
    def category(self) -> str:
        return self.issue_category

    @property
    def confidence(self) -> float:
        return self.confidence_score

    @property
    def excerpt(self) -> str:
        return self.flagged_text

    @property
    def explanation(self) -> str:
        return self.explanation_reason

    @property
    def suggested_rewrite(self) -> Optional[str]:
        return self.suggested_correction


class PluginToneAnalysisResult(BaseModel):
    """Aggregate output from an AI analyzer plugin execution."""
    findings: list[PluginToneFinding] = Field(default_factory=list)
    model_name: str = Field("default-model", description="Identifier of the model or prompt variant used")
    prompt_tokens_used: int = Field(0, ge=0)
    completion_tokens_used: int = Field(0, ge=0)
    latency_ms: float = Field(0.0, ge=0.0)
    summary_notes: Optional[str] = Field(None, description="High-level qualitative summary of document tone")
    # Additional optional fields for analyzer results
    formality_score: Optional[float] = Field(None, description="Formality score calculated by analyzer")
    sentiment_score: Optional[float] = Field(None, description="Sentiment score calculated by analyzer")
    processing_duration_ms: Optional[float] = Field(None, description="Processing latency in ms")
    plugin_identifier: Optional[str] = Field(None, description="Identifier of plugin and version")
    # Allow extra unexpected fields
    model_config = ConfigDict(frozen=True, extra="allow")

    model_config = ConfigDict(frozen=True)


class PluginClaimContext(BaseModel):
    """Context supplied to verify factual assertions against approved facts."""
    claims_to_verify: list[str] = Field(..., description="List of factual assertion sentences extracted from document")
    brand_name: str = Field(..., description="Enterprise brand name")
    approved_facts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Catalog of verified organization facts with temporal validity windows",
    )
    allow_external_rag: bool = Field(default=False, description="Whether retrieval against external corpora is permitted")

    model_config = ConfigDict(frozen=True)


class PluginClaimFinding(BaseModel):
    """Verification verdict for a single factual claim."""
    claim_text: str = Field(..., description="Exact assertion text evaluated")
    verification_status: str = Field(
        ...,
        description="'VERIFIED', 'CONTRADICTED', 'NEEDS_VERIFICATION', 'STALE_FACT'"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    supporting_fact_id: Optional[str] = Field(None, description="Identifier of approved fact used as citation ground")
    citation_snippet: Optional[str] = Field(None, description="Exact factual text supporting or contradicting the claim")
    explanation: str = Field(..., description="Grounding justification")

    model_config = ConfigDict(frozen=True)


# ==============================================================================
# 2. Pydantic v2 Contracts for Vector Retriever Plugins
# ==============================================================================

class PluginRetrievalQuery(BaseModel):
    """Standardized semantic search query passed to Vector Retriever plugins."""
    query_text: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    similarity_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    filter_metadata: dict[str, Any] = Field(default_factory=dict)
    candidate_pool: list[Any] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True, extra="allow")


class PluginRetrievedDocument(BaseModel):
    """Single semantic search hit returned by Vector Retriever plugin."""
    document_id: str
    content: str
    score: float = Field(..., ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)

    @property
    def id(self) -> str:
        return self.document_id

    @property
    def text(self) -> str:
        return self.content


# ==============================================================================
# 3. Isolated Strategy Interfaces (Zero Database / FastAPI Dependencies)
# ==============================================================================

class BaseAIAnalyzerPlugin(ABC):
    """
    Strategy Interface for custom NLP/LLM analyzers.
    AI teammates implement this abstract class to evaluate tone, style, and factual claims
    without needing any knowledge of PostgreSQL, SQLAlchemy, or FastAPI routers.
    """

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """Unique identifier for this analyzer strategy (e.g. 'gpt-4o-tone-v2', 'claude-3-5-sonnet-audit')."""
        pass

    @property
    @abstractmethod
    def plugin_version(self) -> str:
        """SemVer string (e.g. '1.2.0')."""
        pass

    @abstractmethod
    async def analyze_tone(self, context: PluginDocumentContext) -> PluginToneAnalysisResult:
        """
        Executes tone and messaging analysis against brand guidelines.
        Must return a structured PluginToneAnalysisResult.
        """
        pass

    @abstractmethod
    async def verify_claims(self, context: PluginClaimContext) -> list[PluginClaimFinding]:
        """
        Verifies extracted factual assertions against approved facts.
        Claims without verified ground truth MUST be marked 'NEEDS_VERIFICATION'.
        """
        pass

    async def run_benchmark_sample(
        self,
        sample_text: str,
        ground_truth_categories: list[str],
    ) -> dict[str, Any]:
        """
        Optional benchmark hook to run accuracy/precision/recall evaluation against a labelled sample.
        """
        context = PluginDocumentContext(
            content_text=sample_text,
            brand_name="BenchmarkBrand",
        )
        res = await self.analyze_tone(context)
        detected_categories = [f.issue_category for f in res.findings]
        tp = len(set(detected_categories).intersection(ground_truth_categories))
        fp = len(set(detected_categories) - set(ground_truth_categories))
        fn = len(set(ground_truth_categories) - set(detected_categories))
        return {
            "plugin": self.plugin_name,
            "detected_categories": detected_categories,
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "latency_ms": res.latency_ms,
        }


class BaseVectorRetrieverPlugin(ABC):
    """
    Strategy Interface for semantic search and retrieval engines.
    AI teammates implement this class to test alternative embedding models (e.g. Cohere, text-embedding-3-large,
    BGE-M3) or custom Reranking algorithms (e.g. Cross-Encoders).
    """

    @property
    @abstractmethod
    def retriever_name(self) -> str:
        """Unique identifier for this retrieval strategy (e.g. 'bge-m3-hybrid', 'cohere-embed-v3')."""
        pass

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Generates embedding vector for a search query string."""
        pass

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generates batch embedding vectors for documents or guidelines."""
        pass

    @abstractmethod
    async def retrieve_relevant_guidelines(
        self,
        query: PluginRetrievalQuery,
        corpus: list[PluginRetrievedDocument],
    ) -> list[PluginRetrievedDocument]:
        """Ranks and retrieves top-k guideline documents matching query."""
        pass

    @abstractmethod
    async def retrieve_relevant_facts(
        self,
        query: PluginRetrievalQuery,
        corpus: list[PluginRetrievedDocument],
    ) -> list[PluginRetrievedDocument]:
        """Ranks and retrieves top-k approved fact documents matching query."""
        pass


# ==============================================================================
# 4. Central Plugin Registry for Runtime Strategy Selection
# ==============================================================================

class AIPluginRegistry:
    """Thread-safe registry mapping strategy identifiers to plugin instances."""
    _analyzers: dict[str, BaseAIAnalyzerPlugin] = {}
    _retrievers: dict[str, BaseVectorRetrieverPlugin] = {}

    @classmethod
    def register_analyzer(cls, plugin: BaseAIAnalyzerPlugin) -> None:
        cls._analyzers[plugin.plugin_name] = plugin

    @classmethod
    def get_analyzer(cls, plugin_name: str) -> Optional[BaseAIAnalyzerPlugin]:
        return cls._analyzers.get(plugin_name)

    @classmethod
    def list_analyzers(cls) -> list[str]:
        return list(cls._analyzers.keys())

    @classmethod
    def register_retriever(cls, plugin: BaseVectorRetrieverPlugin) -> None:
        cls._retrievers[plugin.retriever_name] = plugin

    @classmethod
    def get_retriever(cls, retriever_name: str) -> Optional[BaseVectorRetrieverPlugin]:
        return cls._retrievers.get(retriever_name)

    @classmethod
    def list_retrievers(cls) -> list[str]:
        return list(cls._retrievers.keys())

    @classmethod
    def clear(cls) -> None:
        cls._analyzers.clear()
        cls._retrievers.clear()
