"""
BrandShield AI - Unit & Domain Verification Test Suite
Tests SHA-256 hash chaining, Git-like revision diffing, and confidence triage rules.
"""

from datetime import datetime, timezone
import pytest

from app.domain.enums import (
    CreatorAction,
    DetectorSource,
    FindingCategory,
    SeverityLevel,
    TriageStatus,
)
from app.services.audit_service import GENESIS_HASH, AuditService
from app.services.finding_triage_service import FindingTriageService
from app.services.submission_service import SubmissionService


def test_audit_hash_calculation_determinism():
    """Validates deterministic SHA-256 digest computation."""
    payload = {"submission_id": "123", "action": "INGEST"}
    hash1 = AuditService._compute_hash(
        previous_hash=GENESIS_HASH,
        actor_id=None,
        action="DOCUMENT_SUBMITTED",
        payload=payload,
        salt="test_salt",
        timestamp_str="2026-10-23T12:00:00Z",
    )
    hash2 = AuditService._compute_hash(
        previous_hash=GENESIS_HASH,
        actor_id=None,
        action="DOCUMENT_SUBMITTED",
        payload=payload,
        salt="test_salt",
        timestamp_str="2026-10-23T12:00:00Z",
    )
    assert hash1 == hash2
    assert len(hash1) == 64


def test_submission_diff_calculation():
    """Tests RFC-style line diff computation between revisions."""
    old_text = "Line 1\nLine 2\nLine 3"
    new_text = "Line 1\nLine 2 modified\nLine 3\nLine 4"
    diff = SubmissionService.compute_diff(old_text, new_text)

    assert diff["lines_added"] >= 2
    assert diff["lines_removed"] >= 1
    assert any("Line 2 modified" in line for line in diff["diff_lines"])


def test_finding_triage_classification_boundaries():
    """Verifies tri-state triage classification and zero-hallucination rules."""
    # Stale fact takes precedence
    status_stale = FindingTriageService.classify_triage(
        confidence_score=0.99,
        has_grounding_evidence=True,
        is_stale_fact=True,
    )
    assert status_stale == TriageStatus.STALE_FACT_REVERIFY

    # Missing evidence mandates Needs Verification
    status_unverified = FindingTriageService.classify_triage(
        confidence_score=0.95,
        has_grounding_evidence=False,
        is_stale_fact=False,
    )
    assert status_unverified == TriageStatus.NEEDS_VERIFICATION_MISSING_EVIDENCE

    # High confidence with evidence -> Auto-flagged
    status_high = FindingTriageService.classify_triage(
        confidence_score=0.92,
        has_grounding_evidence=True,
        is_stale_fact=False,
    )
    assert status_high == TriageStatus.FLAGGED_HIGH_CONFIDENCE

    # Ambiguous / Low confidence -> Routed to human queue
    status_low = FindingTriageService.classify_triage(
        confidence_score=0.75,
        has_grounding_evidence=True,
        is_stale_fact=False,
    )
    assert status_low == TriageStatus.ROUTED_TO_HUMAN_LOW_CONFIDENCE
