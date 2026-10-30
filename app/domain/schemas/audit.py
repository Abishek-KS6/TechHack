"""
BrandShield AI - Pydantic v2 Domain Schemas for Hash-Chained Audit Ledger.
"""

import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class AuditLedgerBase(BaseModel):
    action: str = Field(..., min_length=2, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class AuditLedgerCreate(AuditLedgerBase):
    workspace_id: Optional[uuid.UUID] = None
    actor_id: Optional[uuid.UUID] = None
    previous_hash: str = Field(..., min_length=64, max_length=64)
    current_hash: str = Field(..., min_length=64, max_length=64)


class AuditLedgerRead(AuditLedgerBase):
    sequence_id: int
    workspace_id: Optional[uuid.UUID]
    actor_id: Optional[uuid.UUID]
    previous_hash: str
    current_hash: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditChainVerificationResult(BaseModel):
    is_valid: bool
    total_records: int
    tampered_sequence_id: Optional[int] = None
    verification_message: str
    has_historical_break: bool = False
    historical_break_notes: Optional[str] = None

    @property
    def chain_valid(self) -> bool:
        return self.is_valid

    model_config = ConfigDict(from_attributes=True, extra="allow")
