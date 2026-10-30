"""
BrandShield AI - Workspace Review Rules & Settings Schemas.
"""

from typing import Any
from pydantic import BaseModel, Field


class ReviewRulesSchema(BaseModel):
    """
    Configurable workspace review rules governing triage confidence boundaries,
    anti-automation-bias sampling, factual recertification intervals, and evidence gates.
    """
    confidence_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Confidence threshold (0 to 1) for automated flagging vs human review.",
    )
    random_double_check_percentage: float = Field(
        default=15.0,
        ge=0.0,
        le=100.0,
        description="Stochastic percentage (0 to 100) of high-confidence findings flagged for second review.",
    )
    fact_review_period_days: int = Field(
        default=90,
        ge=1,
        le=3650,
        description="Validity window in days before approved facts require human recertification.",
    )
    require_evidence_before_approval: bool = Field(
        default=True,
        description="Whether all findings must be backed by cited evidence or resolved before reviewer sign-off.",
    )

    model_config = {
        "extra": "ignore",
    }


class ReviewRulesUpdate(BaseModel):
    """Payload for updating workspace review rules (Administrator only)."""
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    random_double_check_percentage: float = Field(ge=0.0, le=100.0)
    fact_review_period_days: int = Field(ge=1, le=3650)
    require_evidence_before_approval: bool

    model_config = {
        "extra": "ignore",
    }

