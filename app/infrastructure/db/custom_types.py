"""
BrandShield AI - Dual-Dialect Vector & Full-Text Search Custom Types.
Provides zero-fragility portability between PostgreSQL (with native pgvector and TSVECTOR)
and zero-config local/CI SQLite (with JSON serialization, in-memory cosine similarity,
and BM25 Reciprocal Rank Fusion).
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Optional

from sqlalchemy import BigInteger, JSON, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PG_UUID
from sqlalchemy.dialects.sqlite.base import SQLiteDDLCompiler
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import Computed


# ==============================================================================
# Dual-Dialect DDL Compilers (Compiles PostgreSQL native types on SQLite)
# ==============================================================================

@compiles(BigInteger, "sqlite")
def compile_bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(TSVECTOR, "sqlite")
def compile_tsvector_sqlite(type_, compiler, **kw):
    return "TEXT"


@compiles(PG_UUID, "sqlite")
def compile_pg_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


@compiles(Computed, "sqlite")
def compile_computed_sqlite(element, compiler, **kw):
    text_val = str(element.sqltext.text) if hasattr(element.sqltext, "text") else str(element.sqltext)
    text_val = re.sub(r"to_tsvector\([^,]+,\s*([^)]+)\)", r"(\1)", text_val)
    persisted = " STORED" if element.persisted else " VIRTUAL"
    return f"GENERATED ALWAYS AS ({text_val}){persisted}"


_original_sqlite_get_column_default_string = SQLiteDDLCompiler.get_column_default_string

def _sqlite_get_column_default_string(self, column):
    res = _original_sqlite_get_column_default_string(self, column)
    if res is not None:
        res = re.sub(r"::\w+", "", res)
        res = res.replace("clock_timestamp()", "CURRENT_TIMESTAMP").replace("gen_random_uuid()", "(lower(hex(randomblob(16))))")
    return res

SQLiteDDLCompiler.get_column_default_string = _sqlite_get_column_default_string


class PortableVector(TypeDecorator):
    """
    Dual-Dialect Vector Type:
    - On PostgreSQL: maps to native pgvector.sqlalchemy.Vector(dim).
    - On SQLite/MySQL/other: transparently maps to JSON list of floats.
    """
    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 1536, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.dim = dim

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            import os
            if os.getenv("ENABLE_PGVECTOR", "false").lower() not in ("true", "1", "yes"):
                return dialect.type_descriptor(JSONB())
            try:
                from pgvector.sqlalchemy import Vector
                return dialect.type_descriptor(Vector(self.dim))
            except (ImportError, Exception):
                return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        import os
        if dialect.name == "postgresql" and os.getenv("ENABLE_PGVECTOR", "false").lower() in ("true", "1", "yes"):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        if hasattr(value, "tolist"):
            return value.tolist()
        return value


class PortableSearchVector(TypeDecorator):
    """
    Dual-Dialect Full-Text Search Vector:
    - On PostgreSQL: maps to native TSVECTOR.
    - On SQLite/other: maps to standard Text.
    """
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            try:
                from sqlalchemy.dialects.postgresql import TSVECTOR
                return dialect.type_descriptor(TSVECTOR())
            except ImportError:
                return dialect.type_descriptor(Text())
        return dialect.type_descriptor(Text())


# ==============================================================================
# In-Memory Cosine Similarity & BM25 Reciprocal Rank Fusion (SQLite / CI Mode)
# ==============================================================================

def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Computes cosine similarity between two dense vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def bm25_lexical_score(query: str, document: str, k1: float = 1.5, b: float = 0.75) -> float:
    """
    Lightweight pure-python BM25 lexical score for single document evaluation.
    Matches token frequencies normalized against query length.
    """
    if not query or not document:
        return 0.0
    q_tokens = [t.lower() for t in re.findall(r"\w+", query)]
    d_tokens = [t.lower() for t in re.findall(r"\w+", document)]
    if not q_tokens or not d_tokens:
        return 0.0

    d_len = len(d_tokens)
    score = 0.0
    for q in set(q_tokens):
        tf = d_tokens.count(q)
        if tf > 0:
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * (d_len / 50.0))
            score += numerator / denominator
    return score


def reciprocal_rank_fusion(
    dense_ranks: list[tuple[Any, float]],
    sparse_ranks: list[tuple[Any, float]],
    k: int = 60,
    top_k: int = 10,
) -> list[tuple[Any, float]]:
    """
    Combines dense vector ranks and sparse lexical ranks using standard RRF:
    RRF(d) = sum(1 / (k + rank(d)))
    """
    scores: dict[Any, float] = {}
    item_map: dict[Any, Any] = {}

    for rank, (item, _) in enumerate(dense_ranks, start=1):
        item_id = getattr(item, "id", item)
        item_map[item_id] = item
        scores[item_id] = scores.get(item_id, 0.0) + (1.0 / (k + rank))

    for rank, (item, _) in enumerate(sparse_ranks, start=1):
        item_id = getattr(item, "id", item)
        item_map[item_id] = item
        scores[item_id] = scores.get(item_id, 0.0) + (1.0 / (k + rank))

    ranked = [(item_map[i_id], score) for i_id, score in scores.items()]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:top_k]
