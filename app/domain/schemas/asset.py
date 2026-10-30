"""
BrandShield AI - Approved Brand Asset & Visual Comparison Schemas.
Pydantic v2 schemas for organization brand asset catalogs, perceptual hash matching,
and visual compliance inspection (detecting unapproved, stretched, or outdated logos).
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class AssetMatchStatus(str, Enum):
    """Visual compliance status against the organization's approved catalog."""
    APPROVED_MATCH = "APPROVED_MATCH"
    STRETCHED_OR_DISTORTED = "STRETCHED_OR_DISTORTED"
    OUTDATED_LOGO = "OUTDATED_LOGO"
    UNAPPROVED_ASSET = "UNAPPROVED_ASSET"


class ApprovedBrandAssetCreate(BaseModel):
    """Registration payload for an official approved corporate brand asset."""
    name: str = Field(..., min_length=1, max_length=128, description="Human-readable asset title (e.g. 'Primary Horizontal Logo')")
    asset_type: str = Field(default="LOGO", description="'LOGO', 'ICON', 'PRODUCT_GRAPHIC', 'BADGE'")
    file_name: str = Field(..., description="Original asset file name (e.g. 'logo_primary.png')")
    dhash: str = Field(..., description="64-bit perceptual difference hash in hex format")
    phash: Optional[str] = Field(None, description="64-bit perceptual frequency hash in hex format")
    aspect_ratio: float = Field(..., gt=0.0, description="Exact width/height aspect ratio")
    width_px: int = Field(..., gt=0, description="Native width in pixels")
    height_px: int = Field(..., gt=0, description="Native height in pixels")
    is_deprecated: bool = Field(default=False, description="Flag indicating if this brand asset has been superseded")
    deprecated_replacement_asset_id: Optional[uuid.UUID] = Field(None, description="Pointer to active replacement asset")
    valid_until: Optional[datetime] = Field(None, description="Optional sunset timestamp for time-limited campaign graphics")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary brand asset metadata")


class ApprovedBrandAssetRead(BaseModel):
    """Public read model for an approved brand asset catalog entry."""
    id: uuid.UUID
    brand_profile_id: uuid.UUID
    name: str
    asset_type: str
    file_name: str
    dhash: str
    phash: Optional[str] = None
    aspect_ratio: float
    width_px: int
    height_px: int
    is_deprecated: bool
    deprecated_replacement_asset_id: Optional[uuid.UUID] = None
    valid_until: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssetMatchFinding(BaseModel):
    """
    Granular visual comparison verdict for an extracted image.
    Explicitly labeled as comparing strictly against approved organizational assets only.
    """
    embedded_image_index: int = Field(..., ge=0, description="0-indexed position of image extracted from document")
    source_format: str = Field(..., description="Detected image format (e.g. 'PNG', 'JPEG')")
    embedded_aspect_ratio: float = Field(..., description="Aspect ratio of embedded image")
    embedded_dhash: str = Field(..., description="Perceptual difference hash of embedded image")
    match_status: AssetMatchStatus = Field(
        ...,
        description="Visual compliance classification evaluated strictly against approved organizational assets only",
    )
    is_compliant: bool = Field(..., description="True only if match_status is APPROVED_MATCH")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Matching confidence score")
    hamming_distance: Optional[int] = Field(None, ge=0, description="Bitwise Hamming distance to closest approved asset")
    aspect_ratio_distortion_percent: Optional[float] = Field(
        None, description="Percentage distortion relative to approved native aspect ratio"
    )
    matched_approved_asset_id: Optional[uuid.UUID] = Field(None, description="Link to official approved asset record")
    matched_approved_asset_name: Optional[str] = Field(None, description="Official approved asset title")
    explanation: str = Field(..., description="Detailed visual compliance justification")
    comparison_scope: str = Field(
        default="ORGANIZATIONAL_APPROVED_ASSETS_ONLY",
        description="Legal Notice: This evaluation compares strictly against approved organizational assets only.",
    )


class AssetCatalogMatchingResponse(BaseModel):
    """
    Aggregate visual inspection response for a document submission or uploaded images.
    """
    brand_profile_id: uuid.UUID
    total_images_extracted: int = Field(..., ge=0)
    compliant_assets_count: int = Field(..., ge=0)
    unapproved_assets_count: int = Field(..., ge=0)
    distorted_assets_count: int = Field(..., ge=0)
    outdated_assets_count: int = Field(..., ge=0)
    catalog_size_evaluated: int = Field(..., ge=0)
    findings: list[AssetMatchFinding] = Field(default_factory=list)
    comparison_scope_notice: str = Field(
        default="This visual inspection strictly compares extracted imagery against the organization's catalog of approved brand assets only.",
        description="Legal boundary notice",
    )
    evaluated_at: datetime
