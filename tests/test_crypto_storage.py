"""
BrandShield AI - Unit tests for Transparent Envelope Encryption & At-Rest Storage.
Verifies AES-128-CBC / Fernet cryptographic storage engine behavior.
"""

import pytest
import uuid
from app.core.crypto_storage import CryptoStorageEngine, ENCRYPTION_PREFIX
from app.infrastructure.db.models import DocumentRevision


def test_crypto_storage_encrypt_decrypt_roundtrip():
    plain_text = "This is highly sensitive enterprise marketing material with proprietary numbers: $4.2B revenue."
    
    # 1. Plain text should not be detected as encrypted
    assert not CryptoStorageEngine.is_encrypted(plain_text)
    
    # 2. Encrypt
    cipher_text = CryptoStorageEngine.encrypt_content(plain_text)
    assert cipher_text != plain_text
    assert cipher_text.startswith(ENCRYPTION_PREFIX)
    assert CryptoStorageEngine.is_encrypted(cipher_text)
    
    # 3. Idempotent encryption: encrypting again returns same ciphertext
    re_encrypted = CryptoStorageEngine.encrypt_content(cipher_text)
    assert re_encrypted == cipher_text
    
    # 4. Decrypt
    decrypted = CryptoStorageEngine.decrypt_content(cipher_text)
    assert decrypted == plain_text
    
    # 5. Transparent decryption on unencrypted text returns as-is
    plain_roundtrip = CryptoStorageEngine.decrypt_content(plain_text)
    assert plain_roundtrip == plain_text


def test_crypto_storage_empty_and_corrupted():
    # Empty string handling
    assert CryptoStorageEngine.encrypt_content("") == ""
    assert CryptoStorageEngine.decrypt_content("") == ""
    assert not CryptoStorageEngine.is_encrypted("")
    assert not CryptoStorageEngine.is_encrypted(None)

    # Corrupted ciphertext raises ValueError
    corrupted = f"{ENCRYPTION_PREFIX}invalid_base64_payload_here"
    with pytest.raises(ValueError, match="Corrupted encrypted payload"):
        CryptoStorageEngine.decrypt_content(corrupted)


def test_crypto_storage_should_protect():
    class MockBrandProfile:
        def __init__(self, protected: bool):
            self.privacy_gate_config = {"protected_storage_enabled": protected}

    assert CryptoStorageEngine.should_protect(MockBrandProfile(True)) is True
    assert CryptoStorageEngine.should_protect(MockBrandProfile(False)) is False
    assert CryptoStorageEngine.should_protect(None) is False
    assert CryptoStorageEngine.should_protect(object()) is False


def test_document_revision_get_decrypted_content():
    plain = "Confidential Q4 Merger Forecast"
    cipher = CryptoStorageEngine.encrypt_content(plain)
    
    rev_encrypted = DocumentRevision(
        id=uuid.uuid4(),
        submission_id=uuid.uuid4(),
        revision_number=1,
        content_text=cipher,
        ast_span_map=[],
        created_by_id=uuid.uuid4(),
        sha256_content_hash="mock_hash",
    )
    assert rev_encrypted.get_decrypted_content() == plain

    rev_plain = DocumentRevision(
        id=uuid.uuid4(),
        submission_id=uuid.uuid4(),
        revision_number=1,
        content_text=plain,
        ast_span_map=[],
        created_by_id=uuid.uuid4(),
        sha256_content_hash="mock_hash",
    )
    assert rev_plain.get_decrypted_content() == plain
