"""
BrandShield AI - Core Intelligence Pipeline Test Suite.
Validates the four decoupled analysis stages and master triage orchestrator:
1. Stage 1: Deterministic Rule Engine (O(N) Aho-Corasick, FKGL, Passive Voice, Caps Abuse).
2. Stage 2: Temporal Fact & Hybrid RAG Retrieval Engine (RRF, Staleness, Contradictions, Missing Evidence).
3. Stage 3: Zero-Trust Privacy Gate, PII Scrubber, Circuit Breaker & Sub-30ms Demo Fallback Cache.
4. Stage 4: Confidence Triage Boundaries & Automation-Bias Safeguard.
"""

from datetime import datetime, timedelta, timezone
import time
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest

from app.domain.enums import (
    AuditAction,
    DetectorSource,
    FindingCategory,
    GuidelineCategory,
    SeverityLevel,
    TriageStatus,
    WorkflowState,
)
from app.infrastructure.db.models import (
    ApprovedFact,
    BrandGuideline,
    BrandProfile,
    DocumentRevision,
    Submission,
)
from app.services.analysis.demo_fallback_cache import (
    DemoFallbackCache,
    FallbackLLMResponse,
    hash_sentence,
)
from app.services.analysis.deterministic_engine import (
    AhoCorasickAutomaton,
    DeterministicRuleEngine,
    PatternPayload,
)
from app.services.analysis.privacy_gate import (
    CircuitBreakerState,
    PIIScrubber,
    PrivacyGateRouter,
)
from app.services.analysis.temporal_fact_engine import (
    TemporalFactEngine,
)
from app.services.analysis.triage_orchestrator import (
    TriageOrchestrator,
)


@pytest.fixture
def workspace_id():
    return uuid.uuid4()


@pytest.fixture
def brand_profile_id():
    return uuid.uuid4()


@pytest.fixture
def brand_profile(workspace_id, brand_profile_id):
    now = datetime.now(timezone.utc)
    return BrandProfile(
        id=brand_profile_id,
        workspace_id=workspace_id,
        name="Enterprise B2B Cloud Profile",
        description="Standard enterprise B2B SaaS voice and compliance boundary.",
        tone_parameters={
            "formality": 8.0,
            "max_sentence_length": 25,
            "max_grade_level": 12.0,
        },
        banned_terminology_map={
            "cure": {
                "reason": "Unsubstantiated therapeutic or medicinal claim.",
                "violation_severity": "HIGH",
                "suggested_replacements": ["address", "resolve"],
            },
            "revolutionary": {
                "reason": "Overused promotional puffery.",
                "violation_severity": "MEDIUM",
                "suggested_replacements": ["innovative", "advanced"],
            },
        },
        preferred_terminology_map={
            "on-premise": "on-premises",
            "lead time": "cycle time",
        },
        messaging_rules={
            "required_trademarks": {
                "BrandShield": "BrandShield™",
                "CloudSecure": "CloudSecure®",
            }
        },
        privacy_gate_config={
            "allow_external_llm": False,
            "approved_providers": ["Azure OpenAI"],
            "contract_verified_at": "2026-01-01T00:00:00Z",
            "retention_days": 30,
        },
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def sample_guidelines(brand_profile_id):
    now = datetime.now(timezone.utc)
    return [
        BrandGuideline(
            id=uuid.uuid4(),
            brand_profile_id=brand_profile_id,
            clause_identifier="TERM-01",
            clause_text="Prohibit uncalibrated superlative claims and non-compliant brand terminology.",
            category=GuidelineCategory.TERMINOLOGY,
            severity=SeverityLevel.HIGH,
            embedding=[0.01] * 1536,
            search_vector="prohibit uncalibrated superlative claim",
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
        BrandGuideline(
            id=uuid.uuid4(),
            brand_profile_id=brand_profile_id,
            clause_identifier="LEGAL-TRADEMARK-01",
            clause_text="Mandatory legal trademark registration symbol placement on first product mention.",
            category=GuidelineCategory.TERMINOLOGY,
            severity=SeverityLevel.HIGH,
            embedding=[0.02] * 1536,
            search_vector="mandatory legal trademark registration symbol",
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
        BrandGuideline(
            id=uuid.uuid4(),
            brand_profile_id=brand_profile_id,
            clause_identifier="TONE-01",
            clause_text="Maintain direct, authoritative enterprise tone avoiding colloquial hedging.",
            category=GuidelineCategory.TONE,
            severity=SeverityLevel.MEDIUM,
            embedding=[0.03] * 1536,
            search_vector="authoritative enterprise tone",
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
    ]


# ==============================================================================
# Stage 1: Deterministic Rule Engine Tests
# ==============================================================================

def test_aho_corasick_automaton_word_boundary_safety():
    """Validates Aho-Corasick automaton word-boundary safety and exact substring matching."""
    automaton = AhoCorasickAutomaton(case_sensitive=False)
    payload = PatternPayload(
        term="cure",
        suggested_correction="solution",
        reason="Medical claim forbidden",
        category=FindingCategory.TERMINOLOGY,
        severity=SeverityLevel.HIGH,
        match_type="BANNED",
    )
    automaton.add_pattern("cure", payload)
    automaton.build()

    # Should match standalone word "cure"
    matches_1 = automaton.search("This is a cure for latency.")
    assert len(matches_1) == 1
    start, end, p = matches_1[0]
    assert start == 10
    assert end == 14
    assert p.term == "cure"

    # Should NOT match subword in "secure" or "obscure"
    matches_2 = automaton.search("Our platform is secure and not obscure.")
    assert len(matches_2) == 0


def test_deterministic_engine_banned_terms_detection(brand_profile, sample_guidelines):
    """
    Validates Stage 1:
    - O(N) multi-pattern Aho-Corasick detection of banned terms.
    - DetectorSource = DETERMINISTIC_RULE, Confidence = 1.0, FLAGGED_HIGH_CONFIDENCE.
    - Exact character offsets and direct foreign key link to guideline.
    """
    text = "Our revolutionary platform delivers a cure for high costs."
    findings = DeterministicRuleEngine.analyze_document(
        content_text=text,
        brand_profile=brand_profile,
        guidelines=sample_guidelines,
    )

    banned_findings = [f for f in findings if f.issue_category == FindingCategory.TERMINOLOGY]
    assert len(banned_findings) >= 2

    # Verify 'revolutionary'
    rev = next((f for f in banned_findings if "revolutionary" in f.explanation_reason), None)
    assert rev is not None
    assert rev.confidence_score == 1.0
    assert rev.triage_status == TriageStatus.FLAGGED_HIGH_CONFIDENCE
    assert rev.detector_source == DetectorSource.DETERMINISTIC_RULE
    assert text[rev.start_offset:rev.end_offset].lower() == "revolutionary"
    assert rev.suggested_correction in ("innovative, advanced", "innovative") or "innovative" in rev.suggested_correction
    assert rev.linked_guideline_id is not None

    # Verify 'cure'
    cure = next((f for f in banned_findings if "cure" in f.explanation_reason), None)
    assert cure is not None
    assert cure.confidence_score == 1.0
    assert text[cure.start_offset:cure.end_offset].lower() == "cure"
    assert cure.linked_guideline_id is not None


def test_deterministic_engine_preferred_vocabulary(brand_profile, sample_guidelines):
    """Validates deprecated terms mapping to preferred corporate standard."""
    text = "We support on-premise deployments with short lead time."
    findings = DeterministicRuleEngine.analyze_document(
        content_text=text,
        brand_profile=brand_profile,
        guidelines=sample_guidelines,
    )

    pref_findings = [f for f in findings if "on-premise" in f.explanation_reason or "lead time" in f.explanation_reason]
    assert len(pref_findings) == 2

    on_prem = next(f for f in pref_findings if "on-premise" in f.explanation_reason)
    assert on_prem.suggested_correction == "on-premises"
    assert text[on_prem.start_offset:on_prem.end_offset] == "on-premise"


def test_deterministic_engine_case_sensitive_trademark(brand_profile, sample_guidelines):
    """
    Validates case-sensitive required trademark checks.
    Missing symbol triggers violation, existing symbol does not.
    """
    text_missing = "Welcome to BrandShield for enterprise data integrity."
    findings_missing = DeterministicRuleEngine.analyze_document(
        content_text=text_missing,
        brand_profile=brand_profile,
        guidelines=sample_guidelines,
    )
    tm_findings = [f for f in findings_missing if "Trademark" in f.explanation_reason]
    assert len(tm_findings) == 1
    assert tm_findings[0].suggested_correction == "BrandShield™"
    assert tm_findings[0].confidence_score == 1.0

    # Text with symbol already present must not trigger
    text_compliant = "Welcome to BrandShield™ for enterprise data integrity."
    findings_compliant = DeterministicRuleEngine.analyze_document(
        content_text=text_compliant,
        brand_profile=brand_profile,
        guidelines=sample_guidelines,
    )
    tm_compliant = [f for f in findings_compliant if "BrandShield" in f.explanation_reason and "Trademark" in f.explanation_reason]
    assert len(tm_compliant) == 0


def test_deterministic_accessibility_and_readability(brand_profile, sample_guidelines):
    """
    Validates readability metrics:
    - Flesch-Kincaid grade level calculation.
    - Sentence length threshold exceeding brand ceiling.
    - Passive voice regex detection.
    - ALL-CAPS abuse detection with acronym whitelisting.
    """
    # Excessive length & complex vocabulary (>25 words)
    long_sentence = (
        "The multifaceted interoperability parameters were painstakingly implemented by our cross-functional consortium "
        "to facilitate instantaneous cryptographic reconciliation across distributed heterogeneous enterprise architectures "
        "without experiencing noticeable system downtime or transaction latency."
    )
    findings = DeterministicRuleEngine.analyze_document(
        content_text=long_sentence,
        brand_profile=brand_profile,
        guidelines=sample_guidelines,
    )

    # Sentence length finding
    len_finding = next((f for f in findings if "readability threshold" in f.explanation_reason), None)
    assert len_finding is not None
    assert len_finding.confidence_score == 1.0
    assert len_finding.suggested_correction == "Split into shorter, concise sentences."

    # Passive voice finding ("were painstakingly implemented")
    pv_finding = next((f for f in findings if "Passive voice" in f.explanation_reason), None)
    assert pv_finding is not None
    assert pv_finding.confidence_score == 1.0

    # Test ALL-CAPS abuse
    caps_text = "This platform is UNBELIEVABLE and compliant with FDA and SOC2 standards."
    caps_findings = DeterministicRuleEngine.analyze_document(
        content_text=caps_text,
        brand_profile=brand_profile,
        guidelines=sample_guidelines,
    )

    # UNBELIEVABLE should trigger
    unbelievable = next((f for f in caps_findings if "UNBELIEVABLE" in f.explanation_reason), None)
    assert unbelievable is not None
    assert unbelievable.suggested_correction == "Unbelievable"

    # FDA and SOC2 must be whitelisted and not trigger
    fda = next((f for f in caps_findings if "FDA" in f.explanation_reason), None)
    soc2 = next((f for f in caps_findings if "SOC2" in f.explanation_reason), None)
    assert fda is None
    assert soc2 is None


# ==============================================================================
# Stage 2: Temporal Fact & Hybrid RAG Retrieval Engine Tests
# ==============================================================================

def test_claim_extraction():
    """Validates AST sentence parsing and isolation of factual/quantitative assertions."""
    text = (
        "Our solution delivered 99.99% uptime over the past 3 years. "
        "We are the #1 industry-leading provider for global banks. "
        "Our engineers enjoy writing Python code."
    )
    claims = TemporalFactEngine.extract_claims(text)
    assert len(claims) == 2

    quant_claim = next(c for c in claims if c.claim_type == "QUANTITATIVE")
    assert "99.99%" in quant_claim.extracted_metrics or "99.99" in quant_claim.extracted_metrics[0]

    super_claim = next(c for c in claims if c.claim_type == "SUPERLATIVE")
    assert "#1" in super_claim.extracted_metrics or "industry-leading" in super_claim.extracted_metrics


@pytest.mark.asyncio
async def test_temporal_governance_stale_fact(workspace_id):
    """
    Validates Temporal Fact Governance Rule A:
    Claim matching an approved fact with expiry_date < now() triggers STALE_FACT_REVERIFY,
    linking the expired fact record, owner ID, and source URL.
    """
    owner_id = uuid.uuid4()
    expired_date = datetime.now(timezone.utc) - timedelta(days=45)
    verification_date = expired_date - timedelta(days=180)

    stale_fact = ApprovedFact(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        fact_statement="Platform delivers 99.99% service level agreement uptime.",
        original_source_url="https://compliance.internal.net/sla-cert-2025.pdf",
        evidence_excerpt="Audited 99.99% uptime across production clusters.",
        verification_date=verification_date,
        expiry_date=expired_date,
        responsible_owner_id=owner_id,
        embedding=[0.05] * 1536,
        is_active=True,
    )

    doc_text = "Our platform guarantees 99.99% service level agreement uptime."
    findings = await TemporalFactEngine.evaluate_claims(
        content_text=doc_text,
        workspace_id=workspace_id,
        preloaded_facts=[stale_fact],
    )

    assert len(findings) == 1
    f = findings[0]
    assert f.triage_status == TriageStatus.STALE_FACT_REVERIFY
    assert f.issue_category == FindingCategory.STALE_FACT
    assert f.linked_fact_id == stale_fact.id
    assert str(owner_id) in f.explanation_reason
    assert stale_fact.original_source_url in f.suggested_correction


@pytest.mark.asyncio
async def test_temporal_governance_numerical_contradiction(workspace_id):
    """
    Validates Temporal Fact Governance Rule B:
    Claim contradicting a valid approved fact (e.g. 98.5% vs 99.99%) triggers FLAGGED_HIGH_CONFIDENCE,
    linking linked_fact_id and its original_source_url.
    """
    now = datetime.now(timezone.utc)
    valid_fact = ApprovedFact(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        fact_statement="Our verified uptime SLA is 99.99% across global cloud regions.",
        original_source_url="https://compliance.internal.net/soc2-audit-report.pdf",
        evidence_excerpt="99.99% verified uptime certified by third-party auditor.",
        verification_date=now - timedelta(days=30),
        expiry_date=now + timedelta(days=335),
        responsible_owner_id=uuid.uuid4(),
        embedding=[0.05] * 1536,
        is_active=True,
    )

    # Document asserts a contradictory metric: 98.5%
    doc_text = "Our verified uptime SLA is 98.5% across global cloud regions."
    findings = await TemporalFactEngine.evaluate_claims(
        content_text=doc_text,
        workspace_id=workspace_id,
        preloaded_facts=[valid_fact],
    )

    assert len(findings) == 1
    f = findings[0]
    assert f.triage_status == TriageStatus.FLAGGED_HIGH_CONFIDENCE
    assert f.linked_fact_id == valid_fact.id
    assert "Numerical contradiction" in f.explanation_reason
    assert valid_fact.original_source_url in f.explanation_reason
    assert f.suggested_correction == valid_fact.fact_statement


@pytest.mark.asyncio
async def test_temporal_governance_missing_evidence_safe_harbor(workspace_id):
    """
    Validates Temporal Fact Governance Rule C (Zero-Hallucination Safe Harbor):
    Factual assertion with NO match in approved facts repository:
    - NEVER invent evidence.
    - NEVER claim confirmed violation.
    - triage_status = NEEDS_VERIFICATION_MISSING_EVIDENCE.
    - explanation_reason = 'Supporting evidence unavailable in approved fact repository; needs verification.'
    - linked_fact_id = None.
    """
    # Empty fact repository
    doc_text = "We achieved $150 million ARR and 85% gross margin last quarter."
    findings = await TemporalFactEngine.evaluate_claims(
        content_text=doc_text,
        workspace_id=workspace_id,
        preloaded_facts=[],
    )

    assert len(findings) == 1
    f = findings[0]
    assert f.triage_status == TriageStatus.NEEDS_VERIFICATION_MISSING_EVIDENCE
    assert f.explanation_reason == "Supporting evidence unavailable in approved fact repository; needs verification."
    assert f.linked_fact_id is None
    assert f.suggested_correction is None


def test_rrf_score_computation():
    """Validates Reciprocal Rank Fusion mathematical formula."""
    # RRF = 1/(60 + dense) + 1/(60 + sparse)
    score_both = TemporalFactEngine.compute_rrf_score(dense_rank=1, sparse_rank=1, k=60)
    expected = (1.0 / 61) + (1.0 / 61)
    assert abs(score_both - expected) < 1e-6

    score_dense_only = TemporalFactEngine.compute_rrf_score(dense_rank=2, sparse_rank=None, k=60)
    assert abs(score_dense_only - (1.0 / 62)) < 1e-6


# ==============================================================================
# Stage 3: Zero-Trust Privacy Gate & Circuit-Breaker LLM Router Tests
# ==============================================================================

def test_privacy_gate_clearance_policy_evaluation(brand_profile):
    """Validates zero-trust egress policy evaluation rules."""
    # 1. Disallowed by default
    brand_profile.privacy_gate_config["allow_external_llm"] = False
    cleared, reason = PrivacyGateRouter.evaluate_privacy_clearance(brand_profile)
    assert not cleared
    assert "strictly prohibits" in reason

    # 2. Missing contract verification
    brand_profile.privacy_gate_config["allow_external_llm"] = True
    brand_profile.privacy_gate_config["contract_verified_at"] = None
    cleared, reason = PrivacyGateRouter.evaluate_privacy_clearance(brand_profile)
    assert not cleared
    assert "contract verification timestamp is missing" in reason

    # 3. Excessive data retention
    brand_profile.privacy_gate_config["contract_verified_at"] = "2026-01-01T00:00:00Z"
    brand_profile.privacy_gate_config["retention_days"] = 90
    cleared, reason = PrivacyGateRouter.evaluate_privacy_clearance(brand_profile)
    assert not cleared
    assert "exceeds maximum allowable ceiling" in reason

    # 4. Cleared policy
    brand_profile.privacy_gate_config["retention_days"] = 30
    cleared, reason = PrivacyGateRouter.evaluate_privacy_clearance(brand_profile, requested_provider="Azure OpenAI")
    assert cleared


def test_pii_scrubber_comprehensive():
    """
    Validates regex scrubbing before network egress:
    Redacts emails, phone numbers, SSNs, IPv4 addresses, API keys/secrets, and codenames.
    """
    raw_text = (
        "Contact architect dev.lead@brandshield.ai or call +1-555-839-2091 for details. "
        "Auditor SSN is 123-45-6789 on node 192.168.1.104 with api_key='sk_live_9981249827419827394'. "
        "Status of Project Titan and Project Apollo remains confidential."
    )
    res = PIIScrubber.scrub(raw_text)

    assert res.redaction_count >= 6
    assert "[REDACTED_EMAIL]" in res.sanitized_text
    assert "[REDACTED_PHONE]" in res.sanitized_text
    assert "[REDACTED_SSN]" in res.sanitized_text
    assert "[REDACTED_IP]" in res.sanitized_text
    assert "[REDACTED_SECRET]" in res.sanitized_text
    assert "[REDACTED_CODENAME]" in res.sanitized_text
    assert "dev.lead@brandshield.ai" not in res.sanitized_text
    assert "sk_live_" not in res.sanitized_text
    assert "Project Titan" not in res.sanitized_text


def test_circuit_breaker_state_transitions():
    """Validates CircuitBreakerState CLOSED -> OPEN -> HALF_OPEN transitions."""
    cb = CircuitBreakerState(failure_threshold=3, recovery_time_seconds=1)
    assert cb.state == "CLOSED"
    assert cb.is_available()

    cb.record_failure()
    cb.record_failure()
    assert cb.state == "CLOSED"
    assert cb.is_available()

    # Trip the breaker
    cb.record_failure()
    assert cb.state == "OPEN"
    assert not cb.is_available()

    # Sleep past recovery time
    time.sleep(1.1)
    assert cb.is_available()
    assert cb.state == "HALF_OPEN"

    # Reset on success
    cb.record_success()
    assert cb.state == "CLOSED"
    assert cb.is_available()


def test_demo_fallback_cache_latency_and_pydantic_structure():
    """
    Validates demo-risk mitigation fallback cache:
    1. Latency is guaranteed under 30ms (<5ms typical).
    2. Response is a structured Pydantic FallbackLLMResponse instance.
    3. SHA-256 sentence hashing canonicalization.
    """
    sentence = "Our revolutionary AI platform guarantees 100% cure for revenue stagnation."
    t0 = time.perf_counter()
    response = DemoFallbackCache.get_response(sentence)
    duration_ms = (time.perf_counter() - t0) * 1000

    assert duration_ms < 30.0  # Must be strictly under 30ms
    assert isinstance(response, FallbackLLMResponse)
    assert response.confidence >= 0.85
    assert response.category == "TONE"
    assert response.suggested_rewrite is not None
    assert "revenue" in response.suggested_rewrite.lower()

    # Test sentence hashing normalization
    h1 = hash_sentence("Hello   World!!! ")
    h2 = hash_sentence("hello world")
    assert h1 == h2


@pytest.mark.asyncio
async def test_privacy_gate_router_blocked_dispatches_local_analysis(workspace_id, brand_profile):
    """
    Validates that when external AI is disallowed, the router executes
    local heuristic tone analysis and records PRIVACY_GATE_BLOCKED_EXTERNAL_AI.
    """
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    brand_profile.privacy_gate_config["allow_external_llm"] = False
    text = "We are gonna deploy tons of stuff next month."

    findings = await PrivacyGateRouter.analyze_tone_and_messaging(
        content_text=text,
        brand_profile=brand_profile,
        workspace_id=workspace_id,
        session=mock_session,
    )

    assert len(findings) >= 1
    f = findings[0]
    assert f.issue_category == FindingCategory.TONE
    assert f.detector_source == DetectorSource.DETERMINISTIC_RULE
    assert f.confidence_score >= 0.85
    assert f.suggested_correction is not None

    # Check that audit ledger logged blocked external AI
    mock_session.add.assert_called()
    logged_event = mock_session.add.call_args[0][0]
    assert logged_event.action == AuditAction.PRIVACY_GATE_BLOCKED_EXTERNAL_AI


# ==============================================================================
# Stage 4: Master Confidence Triage & Automation-Bias Safeguard Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_triage_confidence_boundaries_and_guideline_links(brand_profile, sample_guidelines):
    """
    Validates Stage 4 calibrated routing rules:
    - AI findings with confidence >= 0.85 AND valid guideline/fact link -> FLAGGED_HIGH_CONFIDENCE.
    - AI findings with 0.40 <= confidence < 0.85 -> ROUTED_TO_HUMAN_LOW_CONFIDENCE.
    - AI findings with confidence >= 0.85 but NO valid link -> ROUTED_TO_HUMAN_LOW_CONFIDENCE.
    """
    rev_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    mock_submission = Submission(
        id=uuid.uuid4(),
        workspace_id=brand_profile.workspace_id,
        brand_profile_id=brand_profile.id,
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.SUBMITTED,
    )
    mock_rev = DocumentRevision(
        id=rev_id,
        submission_id=mock_submission.id,
        revision_number=1,
        content_text="Sample text",
        created_by_id=uuid.uuid4(),
        sha256_content_hash="a" * 64,
        ast_span_map=[],
    )

    async def mock_get(model, ident):
        if model == DocumentRevision:
            return mock_rev
        if model == Submission:
            return mock_submission
        return None

    mock_session.get.side_effect = mock_get

    # Allow external AI so tone findings are produced
    brand_profile.privacy_gate_config["allow_external_llm"] = True
    brand_profile.privacy_gate_config["contract_verified_at"] = "2026-01-01T00:00:00Z"
    brand_profile.privacy_gate_config["retention_days"] = 30

    content = "Customers are blown away by our unmatched speed and zero downtime."

    result = await TriageOrchestrator.run_pipeline(
        session=mock_session,
        revision_id=rev_id,
        brand_profile_id=brand_profile.id,
        workspace_id=brand_profile.workspace_id,
        content_text=content,
        preloaded_profile=brand_profile,
        preloaded_guidelines=sample_guidelines,
        audit_sample_rate=0.0,  # disable random audits for this test
    )

    assert result.total_findings > 0
    # Workflow state must transition to TRIAGED
    assert mock_submission.workflow_state == WorkflowState.TRIAGED

    # Ensure findings with valid links and >= 0.85 confidence are FLAGGED_HIGH_CONFIDENCE
    for f in result.findings:
        if f.confidence_score >= 0.85 and (f.linked_guideline_id or f.linked_fact_id):
            assert f.triage_status in (
                TriageStatus.FLAGGED_HIGH_CONFIDENCE,
                TriageStatus.STALE_FACT_REVERIFY,
            )
        elif 0.40 <= f.confidence_score < 0.85:
            assert f.triage_status in (
                TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE,
                TriageStatus.NEEDS_VERIFICATION_MISSING_EVIDENCE,
            )


@pytest.mark.asyncio
async def test_automation_bias_safeguard_stochastic_injection(brand_profile, sample_guidelines):
    """
    Validates Stage 4 Automation-Bias Safeguard:
    Stochastically selects FLAGGED_HIGH_CONFIDENCE findings, sets is_automation_bias_audit = True,
    prepends explicit verification warning, and logs STOCHASTIC_AUDIT_INJECTED into audit ledger.
    """
    rev_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    mock_submission = Submission(
        id=uuid.uuid4(),
        workspace_id=brand_profile.workspace_id,
        brand_profile_id=brand_profile.id,
        creator_id=uuid.uuid4(),
        workflow_state=WorkflowState.SUBMITTED,
    )
    mock_rev = DocumentRevision(
        id=rev_id,
        submission_id=mock_submission.id,
        revision_number=1,
        content_text="Prohibited cure",
        created_by_id=uuid.uuid4(),
        sha256_content_hash="a" * 64,
        ast_span_map=[],
    )

    async def mock_get(model, ident):
        if model == DocumentRevision:
            return mock_rev
        if model == Submission:
            return mock_submission
        return None

    mock_session.get.side_effect = mock_get

    # Text that triggers deterministic banned term 'cure' -> 1.0 confidence FLAGGED_HIGH_CONFIDENCE
    content = "Our product provides a cure for complexity."

    # Force 100% audit sampling rate to verify safeguard execution deterministically
    result = await TriageOrchestrator.run_pipeline(
        session=mock_session,
        revision_id=rev_id,
        brand_profile_id=brand_profile.id,
        workspace_id=brand_profile.workspace_id,
        content_text=content,
        preloaded_profile=brand_profile,
        preloaded_guidelines=sample_guidelines,
        audit_sample_rate=1.0,
    )

    assert result.automation_bias_audits_injected >= 1

    audited_finding = next(f for f in result.findings if f.is_automation_bias_audit)
    assert audited_finding is not None
    assert "[AUTOMATION-BIAS SAFEGUARD:" in audited_finding.explanation_reason

    # Verify audit ledger recorded STOCHASTIC_AUDIT_INJECTED
    added_objects = [call[0][0] for call in mock_session.add.call_args_list]
    audit_events = [obj for obj in added_objects if hasattr(obj, "action") and obj.action == AuditAction.STOCHASTIC_AUDIT_INJECTED]
    assert len(audit_events) >= 1
    assert audit_events[0].workspace_id == brand_profile.workspace_id
