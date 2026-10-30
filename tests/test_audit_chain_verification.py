"""
BrandShield AI - Audit Chain Cryptographic Verification Test Suite.
Validates SHA-256 hash chaining, Merkle-style tamper detection, and verification algorithms.
"""

from datetime import datetime, timezone
import hashlib
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest

from app.domain.enums import AuditAction
from app.infrastructure.db.models import AuditLedger
from app.services.audit_service import GENESIS_HASH, AuditService


def test_audit_hash_formula_conformance():
    """
    Verifies that compute_hash strictly follows:
    SHA-256(previous_hash + actor_id + action + canonical_json(payload) + timestamp).
    """
    prev_hash = "0" * 64
    actor_id = uuid.uuid4()
    action = AuditAction.DOCUMENT_SUBMITTED
    payload = {"document_id": "doc-99", "pages": 12, "sensitive": False}
    timestamp = "2026-10-24T12:00:00+00:00"

    canonical_payload = AuditService.canonical_json(payload)
    # Expected manually formatted string
    expected_digest_input = f"{prev_hash}{str(actor_id)}{action.value}{canonical_payload}{timestamp}"
    expected_sha256 = hashlib.sha256(expected_digest_input.encode("utf-8")).hexdigest()

    computed = AuditService.compute_hash(
        previous_hash=prev_hash,
        actor_id=actor_id,
        action=action,
        payload=payload,
        timestamp_str=timestamp,
    )
    assert computed == expected_sha256


@pytest.mark.asyncio
async def test_audit_chain_verification_on_valid_ledger():
    """Verifies that an intact sequential ledger passes verification cleanly."""
    mock_session = AsyncMock()

    records = []
    prev_hash = GENESIS_HASH
    now = datetime.now(timezone.utc)
    ts_str = now.isoformat()

    for seq in range(1, 4):
        actor = uuid.uuid4()
        action = AuditAction.FACT_VERIFIED.value
        payload = {"fact_id": f"fact-{seq}", "status": "VERIFIED"}
        curr_hash = AuditService.compute_hash(
            previous_hash=prev_hash,
            actor_id=actor,
            action=action,
            payload=payload,
            timestamp_str=ts_str,
        )
        record = AuditLedger(
            sequence_id=seq,
            workspace_id=uuid.uuid4(),
            actor_id=actor,
            action=action,
            payload=payload,
            previous_hash=prev_hash,
            current_hash=curr_hash,
            timestamp=now,
        )
        records.append(record)
        prev_hash = curr_hash

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = records
    mock_session.execute.return_value = mock_result

    verification = await AuditService.verify_chain_integrity(session=mock_session)
    assert verification.is_valid is True
    assert verification.total_records == 3
    assert verification.tampered_sequence_id is None


@pytest.mark.asyncio
async def test_audit_chain_verification_detects_tampered_payload():
    """Verifies that payload tampering at sequence N is detected and flagged."""
    mock_session = AsyncMock()

    records = []
    prev_hash = GENESIS_HASH
    now = datetime.now(timezone.utc)
    ts_str = now.isoformat()

    for seq in range(1, 4):
        actor = uuid.uuid4()
        action = AuditAction.DOCUMENT_SUBMITTED.value
        payload = {"doc_id": seq}
        curr_hash = AuditService.compute_hash(
            previous_hash=prev_hash,
            actor_id=actor,
            action=action,
            payload=payload,
            timestamp_str=ts_str,
        )
        record = AuditLedger(
            sequence_id=seq,
            workspace_id=uuid.uuid4(),
            actor_id=actor,
            action=action,
            payload=payload,
            previous_hash=prev_hash,
            current_hash=curr_hash,
            timestamp=now,
        )
        records.append(record)
        prev_hash = curr_hash

    # Malicious actor tampers with payload of sequence 2
    records[1].payload = {"doc_id": 2, "tampered": True}

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = records
    mock_session.execute.return_value = mock_result

    verification = await AuditService.verify_chain_integrity(session=mock_session)
    assert verification.is_valid is False
    assert verification.tampered_sequence_id == 2
    assert "Hash tampering detected" in verification.verification_message
