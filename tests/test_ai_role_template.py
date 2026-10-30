# tests/test_ai_role_template.py

import asyncio
import pytest
from app.services.analysis.plugins.ai_role_template import (
    TeammateAIAnalyzerPlugin,
    TeammateVectorRetrieverPlugin,
    PluginDocumentContext,
    PluginRetrievalQuery,
    PluginRetrievedDocument,
)

@pytest.mark.asyncio
async def test_analyzer_returns_valid_result():
    plugin = TeammateAIAnalyzerPlugin()
    context = PluginDocumentContext(
        content_text="Our product is 100% risk-free and unbeatable.",
        brand_name="TestBrand",
        prohibited_terms=["risk-free", "unbeatable"],
        guidelines=[],
    )
    result = await plugin.analyze_tone(context)
    assert hasattr(result, "findings")
    assert isinstance(result.findings, list)
    assert any(f.category == "TERMINOLOGY" for f in result.findings)

@pytest.mark.asyncio
async def test_vector_retriever_ranks_candidates():
    retriever = TeammateVectorRetrieverPlugin(dense_weight=0.6, sparse_weight=0.4)
    docs = [
        PluginRetrievedDocument(document_id="1", content="doc one", score=0.0, metadata={}),
        PluginRetrievedDocument(document_id="2", content="doc two", score=0.0, metadata={}),
    ]
    candidates = [
        type("Doc", (), {"id": d.document_id, "text": d.content, "metadata": d.metadata}) for d in docs
    ]
    query = PluginRetrievalQuery(
        query_text="test query",
        top_k=2,
        similarity_threshold=0.0,
        filter_metadata={},
        candidate_pool=candidates,
    )
    ranked = await retriever.rank_candidates(query)
    assert isinstance(ranked, list)
    assert len(ranked) == 2
    assert ranked[0].score >= ranked[1].score
