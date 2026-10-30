"""
BrandShield AI - AI Analysis Plugins Package.
Directory where AI team members drop custom analyzer strategies and retrievers.
"""

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

__all__ = [
    "AIPluginRegistry",
    "BaseAIAnalyzerPlugin",
    "BaseVectorRetrieverPlugin",
    "PluginClaimContext",
    "PluginClaimFinding",
    "PluginDocumentContext",
    "PluginRetrievalQuery",
    "PluginRetrievedDocument",
    "PluginToneAnalysisResult",
    "PluginToneFinding",
]
