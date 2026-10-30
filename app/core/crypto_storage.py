"""
BrandShield AI - Protected At-Rest Storage & Transparent Envelope Encryption.
Fulfills the Enterprise Privacy & Responsible AI specification by encrypting
sensitive raw content snapshots at rest with symmetric AES-128-CBC / HMAC-SHA256 (Fernet).
"""

import base64
import hashlib
import logging
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger("brandshield.core.crypto_storage")

ENCRYPTION_PREFIX = "enc:fernet:"


class CryptoStorageEngine:
    """
    Symmetric encryption engine for protecting customer confidential content at rest.
    Derives deterministic, cryptographically secure 32-byte Fernet keys from application secrets.
    """
    _fernet: Optional[Fernet] = None

    @classmethod
    def _get_fernet(cls) -> Fernet:
        if cls._fernet is None:
            settings = get_settings()
            raw_secret = getattr(settings, "STORAGE_ENCRYPTION_KEY", None) or settings.SECRET_KEY
            # Derive deterministic 32-byte key via SHA-256 and base64 urlsafe encode
            digest = hashlib.sha256(raw_secret.encode("utf-8")).digest()
            fernet_key = base64.urlsafe_b64encode(digest)
            cls._fernet = Fernet(fernet_key)
        return cls._fernet

    @classmethod
    def is_encrypted(cls, text: Optional[str]) -> bool:
        """Determines if the payload is encrypted under BrandShield envelope."""
        if not text:
            return False
        return text.startswith(ENCRYPTION_PREFIX)

    @classmethod
    def encrypt_content(cls, plain_text: str) -> str:
        """
        Encrypts plaintext string returning ciphertext prefixed with 'enc:fernet:'.
        Idempotent: if already encrypted, returns as-is.
        """
        if not plain_text or cls.is_encrypted(plain_text):
            return plain_text

        f = cls._get_fernet()
        token = f.encrypt(plain_text.encode("utf-8")).decode("utf-8")
        return f"{ENCRYPTION_PREFIX}{token}"

    @classmethod
    def decrypt_content(cls, cipher_text: str) -> str:
        """
        Decrypts ciphertext if prefixed with 'enc:fernet:'.
        If plaintext, transparently returns original string.
        """
        if not cipher_text or not cls.is_encrypted(cipher_text):
            return cipher_text

        raw_token = cipher_text[len(ENCRYPTION_PREFIX):]
        f = cls._get_fernet()
        try:
            return f.decrypt(raw_token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            logger.error("Failed to decrypt envelope token: invalid key or corrupted payload: %s", exc)
            raise ValueError("Corrupted encrypted payload: could not decrypt with active key.") from exc

    @classmethod
    def should_protect(cls, brand_profile: Any) -> bool:
        """Evaluates whether at-rest protected encryption is required for the brand profile."""
        if not brand_profile:
            return False
        config = getattr(brand_profile, "privacy_gate_config", {})
        if isinstance(config, dict):
            return bool(config.get("protected_storage_enabled", False))
        return False
