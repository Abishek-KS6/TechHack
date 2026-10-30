# BrandShield AI

### Enterprise Content Governance, Brand Protection & Evidence-Linked Audit Platform
**Engineered for Tamper-Evident Content Verification and Regulatory Assurance in Regulated Markets**

[![Python 3.13](https://img.shields.io/badge/Python-3.13%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%7C%20pgvector-336791.svg?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![React 19](https://img.shields.io/badge/React-19.0-61dafb.svg?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178c6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Pytest Suite](https://img.shields.io/badge/Tests-159%20Passed-brightgreen.svg?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)

---

## Architecture in One Paragraph

BrandShield AI employs a layered hexagonal architecture combining an asynchronous FastAPI backend and a React 19 single-page frontend. Ingested marketing text, PDFs, and DOCX documents pass through an AST tokenizer into a multi-stage verification pipeline: deterministic Aho-Corasick dictionary scans enforce terminology and readability, temporal fact evaluation grounds factual claims against database-backed corporate truth with validity windows, and an opt-in privacy gate routes tone checks through approved zero-data-retention AI providers with timeout circuit breakers. Confidence-calibrated triage tags each finding with plain-language explanations and guideline evidence links, routing ambiguous spans to human review or `NEEDS_VERIFICATION`. Approved changes append to a Git-style document revision DAG and seal every governance action into a cryptographically chained SHA-256 Merkle audit ledger in PostgreSQL with transactional advisory locks.

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 19, TypeScript 5.7, Vite 6, React Router 7, Recharts, Lucide Icons, Pure CSS |
| **Backend API** | Python 3.13+, FastAPI, Pydantic v2, Uvicorn, Asyncio |
| **Persistence & Vector** | PostgreSQL 16+ with `pgvector` extension, SQLAlchemy 2.0 Async, Alembic |
| **Parsing & NLP** | Pure-Python Aho-Corasick Automaton, PyMuPDF (`fitz`), python-docx, Flesch-Kincaid AST |
| **Security & Cryptography** | SHA-256 hash-chained Merkle ledger, Argon2id password hashing, JWT Bearer tokens |
| **Testing & CI** | Pytest, Pytest-Asyncio, HTTPX, Coverage |

---

## Core Implemented Capabilities

1. **Evidence-Linked Findings**:
   - Every compliance finding returned by `/api/v1/analysis/live` includes:
     - Plain-language explanation rationale.
     - Severity classification (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
     - Explicit evidence link or citation back to the active brand guideline or verified corporate fact record.
   - Any finding lacking direct supporting evidence receives the status `NEEDS_VERIFICATION` (labeled "Needs verification" in the UI), preventing hallucinated or unsubstantiated violation verdicts.
   - Low-confidence or ambiguous findings (< 0.85 confidence score) route automatically to human specialist review rather than auto-flagging.
   - Confidence scores are explicitly presented in the UI as a **prioritisation signal**, never as conclusive proof of correctness.

2. **Automation-Bias Safeguard**:
   - A configurable 15% (`AUTOMATION_BIAS_SAMPLE_RATE=0.15`) stochastic second-check injects random review requirements into high-confidence findings to prevent reviewer rubber-stamping.
   - Every stochastic injection is recorded in the immutable audit ledger (`STOCHASTIC_AUDIT_INJECTED`).
   - The Reviewer UI mandates manual evidence review before approving any submission.

3. **Human Review Workflow Completeness**:
   - End-to-end Creator actions:
     - **Accept Suggestion**: Replaces text and commits revision `vN+1` to the revision DAG.
     - **Custom Edit**: Allows the Creator to provide their own revision text and rationale.
     - **Reject with Rationale**: Records why a suggestion was dismissed without altering document text.
   - End-to-end Reviewer actions:
     - Full review decision capture (`APPROVED`, `CHANGES_REQUESTED`) with reviewer commentary and verification checklist.
     - Comments are stored in PostgreSQL and rendered chronologically in the submission revision history.
   - Strict invariants:
     - **Zero Silent Overwrites**: Original genesis document text is preserved immutably.
     - **Zero Auto-Publishing**: Automated algorithms cannot mark documents approved; human authorization is mandatory.

4. **Governance Reporting & Aggregations**:
   - Endpoint `/governance/reports` aggregates compliance metrics grouped by issue category (`TONE`, `TERMINOLOGY`, `UNSUBSTANTIATED_CLAIMS`, `STALE_FACTS`).
   - All charts on the Dashboard and Governance pages read live backend database telemetry. Benchmark comparison datasets are explicitly marked as `(Sample Benchmark)`.

5. **Tamper-Evident Audit Ledger Integrity**:
   - Cryptographically linked SHA-256 hash chain: `H_n = SHA-256(H_{n-1} || actor_id || action || payload || timestamp)`.
   - Concurrency safety enforced via PostgreSQL transaction-level advisory locks (`pg_advisory_xact_lock(0x50474155444954)`).
   - Preserved historical break at sequence #9:
     - Sequence #8 and #9 were created concurrently in an early multi-worker test prior to the advisory lock introduction.
     - Both point to parent sequence #7, creating a historical fork.
     - Per zero-tampering ground rules, historical records are preserved intact. The verification service checks sequence #1 through #8, records `known historical break at #9 (pre-fix, preserved)`, and verifies integrity from block #10 onward.

6. **Demo Reliability & Offline Fallback**:
   - External LLM requests include an `asyncio.wait_for` timeout watchdog.
   - When external AI latency exceeds threshold or fails, the engine falls back to pre-verified offline examples (< 30ms latency), ensuring the live demo remains responsive.
   - `DEMO_MODE=true` enables predictable sample execution.

---

## Local Setup & Quickstart

### Prerequisites
- Python 3.11+ (Python 3.13 recommended)
- Node.js 18+ and npm
- PostgreSQL 16+ (or local SQLite fallback)

### 1. Clone & Configure Environment
```bash
git clone https://github.com/your-org/BrandShield_AI.git
cd BrandShield_AI
cp .env.example .env
```

### 2. Backend Setup
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations and seed demo data
alembic upgrade head
python -m app.infrastructure.db.seed

# Start backend server (runs on http://localhost:8000)
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Build or run development server (runs on http://localhost:5173)
npm run dev
```

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/brandshield` |
| `SECRET_KEY` | JWT signing secret key (min 32 bytes) | `brandshield_demo_secret_key_change_in_production...` |
| `ALGORITHM` | JWT cryptographic algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session validity duration | `1440` (24 hours) |
| `DEMO_MODE` | Enable instant fallback cache for live demos | `true` |
| `AUTOMATION_BIAS_SAMPLE_RATE` | Fraction of findings flagged for 2nd review | `0.15` (15%) |
| `AI_REQUEST_TIMEOUT_SECONDS` | External AI request timeout watchdog | `4.0` |
| `AZURE_OPENAI_API_KEY` | Optional Azure OpenAI key for tone checks | `None` |
| `CORS_ORIGINS` | Permitted browser origins | `["http://localhost:5173"]` |

---

## Privacy Note & Model Disclosure

- **Data Protection Guarantee**: Confidential documents, draft copy, and brand assets ingested into BrandShield AI are **never used to train foundational AI models**.
- **External AI Policy**: Content is never transmitted to external model providers unless explicitly authorized by workspace administrators via the Privacy Gate configuration (`allow_external_llm: true`).
- **AI Providers Used**:
  - **Deterministic Rule Engine**: Runs locally on CPU using Aho-Corasick automatons and regex AST. No data leaves the server.
  - **Temporal Fact Engine**: Runs against local PostgreSQL embeddings via `pgvector` or local cosine similarity. No data leaves the server.
  - **Optional External Tone Checks**: When enabled, uses **Azure OpenAI Service** under an Enterprise Agreement with a **Zero-Data-Retention policy** (customer content is not logged, retained, or reviewed by Microsoft personnel). If unconfigured or offline, the local fallback cache satisfies requests without external egress.

---

## Known Limitations

1. **Historical Ledger Sequence #9**:
   - In early development test databases, sequence #8 and sequence #9 were committed in parallel by concurrent workers before transaction-level advisory locking was added.
   - As a result, sequence #9's `previous_hash` references sequence #7 instead of #8.
   - In accordance with regulatory audit standards, historical ledger rows are **never edited or deleted**. The audit service explicitly reports `known historical break at #9 (pre-fix, preserved)` and validates all subsequent blocks #10 onwards. Fresh production instances starting from genesis sequence #1 have an unbroken chain.
2. **Offline Fallback Coverage**:
   - If external LLM API credentials are not provided or network access is restricted, tone and messaging checks fall back to pre-verified rule heuristics and cache. Full tone nuance detection requires configuring an enterprise Azure OpenAI or Claude endpoint.
3. **Local SQLite Limitations**:
   - Local development on SQLite uses in-memory cosine similarity and JSON storage. Production deployments should use PostgreSQL 16+ with native `pgvector` HNSW indexing for multi-million vector datasets.

---

## 3-Minute Live Demo Walkthrough

Follow this step-by-step walkthrough to evaluate the complete end-to-end governance lifecycle:

1. **Sign In (0:00 - 0:30)**:
   - Navigate to `http://localhost:5173/login`.
   - Select the **Test role (CREATOR)** account from the Role dropdown (autofills `creator@acme.com`).
   - Click **Sign In →** to enter the workspace dashboard.

2. **Run Live Brand Analysis (0:30 - 1:15)**:
   - Click **Brand Analysis** in the sidebar.
   - Click the template: *"Unsubstantiated Claim: Our revolutionary AI platform provides a 100% foolproof guarantee..."*
   - Click **Analyze Content**.
   - Observe findings:
     - Prohibited Term: *"foolproof"* -> **Flagged** with evidence citation to Brand Guideline `TERM-01`.
     - Ambiguous Claim -> **Needs verification** badge (unconfirmed without source proof).
     - Prioritisation signals displayed as percentage scores.

3. **Accept Suggestion & Commit Revision (1:15 - 1:45)**:
   - Click **Accept Suggestion** on the prohibited term finding.
   - The editor text updates in place, preserving original context and logging the replacement.

4. **Submit for Review & Authorize (1:45 - 2:30)**:
   - Click **Submit Document for Review**.
   - Switch accounts: log out and select **Auditor (REVIEWER)** (`reviewer@acme.com`).
   - Open **Submissions** in the sidebar.
   - Open the submission to view the Unified Diff between Genesis `v1` and Revision `v2`.
   - Complete the reviewer verification checklist (for findings with automation bias audits).
   - Enter sign-off notes: *"Approved with mandatory disclaimer added."*
   - Click **Approve Submission**.

5. **Inspect Governance & Audit Chain (2:30 - 3:00)**:
   - Click **Governance** to inspect live compliance rates, category distribution (Tone, Terminology, Claims, Facts), and SLA metrics.
   - Click **Audit Ledger** in the sidebar.
   - Inspect the cryptographic SHA-256 hash chain and verification status banner confirming tamper-evident chain integrity.

---

## Verification & Testing

Run the full automated test suite (159 passing unit and integration tests):
```bash
# Run full pytest suite
pytest -v

# Run specific audit and governance tests
pytest tests/test_governance_category_counts.py tests/test_automation_bias_safeguard.py tests/test_evidence_linked_findings.py

# Verify frontend TypeScript build
cd frontend && npm run build
```
