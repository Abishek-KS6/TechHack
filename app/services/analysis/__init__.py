"""
BrandShield AI - Core Intelligence & Analysis Services Pipeline
Follows the core architectural principle:
"Objective checks use deterministic rules first. AI is used where judgment is needed."
"""

from app.services.analysis.demo_fallback_cache import (
    DemoFallbackCache,
    FallbackLLMResponse,
    hash_sentence,
    normalize_sentence,
)
from app.services.analysis.deterministic_engine import (
    AhoCorasickAutomaton,
    DeterministicFinding,
    DeterministicRuleEngine,
    PatternPayload,
)
from app.services.analysis.privacy_gate import (
    CircuitBreakerState,
    PIIScrubber,
    PrivacyGateRouter,
    ScrubResult,
    ToneAnalysisFinding,
)
from app.services.analysis.temporal_fact_engine import (
    ExtractedClaim,
    TemporalFactEngine,
    TemporalFactFinding,
)
from app.services.analysis.triage_orchestrator import (
    AUTOMATION_BIAS_SAMPLE_RATE,
    AnalysisPipelineResult,
    TriageOrchestrator,
)

__all__ = [
    "AhoCorasickAutomaton",
    "PatternPayload",
    "DeterministicFinding",
    "DeterministicRuleEngine",
    "ExtractedClaim",
    "TemporalFactFinding",
    "TemporalFactEngine",
    "ScrubResult",
    "PIIScrubber",
    "CircuitBreakerState",
    "ToneAnalysisFinding",
    "PrivacyGateRouter",
    "FallbackLLMResponse",
    "normalize_sentence",
    "hash_sentence",
    "DemoFallbackCache",
    "AnalysisPipelineResult",
    "TriageOrchestrator",
    "AUTOMATION_BIAS_SAMPLE_RATE",
]
