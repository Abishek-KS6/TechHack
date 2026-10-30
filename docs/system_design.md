# Brand Shield AI — System Design & Architecture Blueprint

This document contains the exact principal-level system design blueprint for **Brand Shield AI**.

See the full authoritative specification in [ARCHITECTURE.md](file:///c:/Users/Admin/OneDrive/Desktop/Brand_shield_AI/ARCHITECTURE.md).

```
+-----------------------------------------------------------------------------------+
|                        API GATEWAY & SECURITY PERIMETER                           |
|   [Rate Limiter] -> [JWT & RBAC Guard (Creator/Reviewer/Admin)] -> [Correlation]  |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                     INGESTION & AST TOKENIZATION ENGINE                           |
|   [Magic-Byte Validator] -> [PyMuPDF / python-docx Parser] -> [Span Offset Map]   |
+-----------------------------------------+-----------------------------------------+
                                          |
                    +---------------------+---------------------+
                    |                                           |
                    v (Stage 1: Sub-ms O(N))                    v (Stage 2: Hybrid RAG)
+---------------------------------------+   +---------------------------------------+
|     DETERMINISTIC RULE AUTOMATON      |   |    TEMPORAL FACT & VECTOR ENGINE      |
| * Aho-Corasick Terminology Matcher    |   | * pgvector HNSW + BM25 RRF Search     |
| * Regex AST Objective Claim Scanner   |   | * Expiry & Verification Date Triage   |
| * Accessibility & Readability Scorer  |   | * Stale Fact Re-verification Trigger  |
+-------------------+-------------------+   +-------------------+-------------------+
                    |                                           |
                    +---------------------+---------------------+
                                          |
                                          v (Stage 3: Conditional Judgment)
+-----------------------------------------------------------------------------------+
|                 ZERO-TRUST PRIVACY GATE & CIRCUIT-BREAKER LLM ROUTER              |
|  [Tenant Policy Check] -> [PII Redactor] -> [Semantic Cache] -> [External LLM]    |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|               CONFIDENCE TRIAGE & AUTOMATION-BIAS SAFEGUARD ENGINE                |
|  * High Confidence -> Flagged + Source Link                                       |
|  * Low/Ambiguous -> Routed to Human Queue                                         |
|  * Missing Evidence -> Marked "Needs Verification" (Evidence-Linked Rule)         |
|  * Stochastic Audit -> Injects Random Double-Check Flags for Reviewers            |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|             IMMUTABLE GIT-LIKE REVISION DAG & POSTGRESQL STORAGE                  |
|  [SHA-256 Hash-Chained Audit Log] | [Diff Patch Engine] | [Materialized Views]    |
+-----------------------------------------------------------------------------------+
```
