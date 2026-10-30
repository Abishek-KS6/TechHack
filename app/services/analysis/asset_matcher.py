"""
BrandShield AI - Approved Brand Asset & Visual Comparison Matcher.
Isolated visual inspection module executing:
1. Multi-format embedded image extraction from PDFs (PyMuPDF) and DOCX (ZIP package inspection).
2. Pure perceptual hashing (dHash difference hash & pHash frequency hash) using PIL.
3. Aspect ratio distortion and stretching detection against approved vector/raster references.
4. Strict evaluation against the organization's approved brand asset catalog only (detecting
   unapproved, stretched, or outdated logos).
"""

from datetime import datetime, timezone
import io
import math
from typing import Any, Optional
import uuid
import zipfile

from PIL import Image

from app.domain.schemas.asset import (
    ApprovedBrandAssetRead,
    AssetCatalogMatchingResponse,
    AssetMatchFinding,
    AssetMatchStatus,
)

try:
    import pymupdf as fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


class VisualAssetMatcher:
    """
    Perceptual visual inspection and brand asset matching engine.
    Compares embedded or uploaded images strictly against the organization's approved catalog.
    """

    ASPECT_RATIO_DISTORTION_TOLERANCE = 0.08  # 8% threshold for stretched/distorted logo detection
    PERCEPTUAL_MATCH_THRESHOLD = 12           # Max Hamming distance for positive identity match (out of 64 bits)

    # --------------------------------------------------------------------------
    # 1. Perceptual Hashing Utilities (Pure Python + PIL)
    # --------------------------------------------------------------------------

    @staticmethod
    def compute_dhash(image: Image.Image, hash_size: int = 8) -> str:
        """
        Computes 64-bit difference hash (dHash) as a 16-character hexadecimal string.
        Grayscale -> Resize to (hash_size + 1, hash_size) -> Horizontal gradient difference.
        Resilient against JPEG compression, scaling, and minor color shifts.
        """
        # Convert to grayscale
        gray = image.convert("L")
        # Resize ignoring aspect ratio to (9, 8) for 8x8 comparison grid
        resized = gray.resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)

        pixels = list(resized.get_flattened_data() if hasattr(resized, "get_flattened_data") else resized.getdata())
        diff_bits: list[int] = []

        # Compare adjacent pixels in each row
        width = hash_size + 1
        for row in range(hash_size):
            row_start = row * width
            for col in range(hash_size):
                left_pixel = pixels[row_start + col]
                right_pixel = pixels[row_start + col + 1]
                diff_bits.append(1 if left_pixel > right_pixel else 0)

        # Convert 64 bits to hex string
        int_val = 0
        for bit in diff_bits:
            int_val = (int_val << 1) | bit
        return f"{int_val:016x}"

    @staticmethod
    def compute_phash(image: Image.Image, hash_size: int = 8) -> str:
        """
        Computes frequency-based perceptual hash (pHash) using discrete cosine representation.
        """
        gray = image.convert("L").resize((32, 32), Image.Resampling.BILINEAR)
        pixels = list(gray.getdata())

        # 2D DCT low-frequency approximation
        # Compute mean intensity of low frequency 8x8 block (excluding DC component [0,0])
        block_values: list[float] = []
        for u in range(hash_size):
            for v in range(hash_size):
                sum_val = 0.0
                for x in range(32):
                    for y in range(32):
                        sum_val += (
                            pixels[y * 32 + x]
                            * math.cos((2 * x + 1) * u * math.pi / 64)
                            * math.cos((2 * y + 1) * v * math.pi / 64)
                        )
                block_values.append(sum_val)

        # Compute median of AC components (skip u=0, v=0)
        ac_values = block_values[1:]
        median_val = sorted(ac_values)[len(ac_values) // 2] if ac_values else 0.0

        int_val = 0
        for val in block_values:
            int_val = (int_val << 1) | (1 if val > median_val else 0)
        return f"{int_val:016x}"

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """Computes bitwise Hamming distance between two 16-character hex hashes."""
        try:
            val1 = int(hash1, 16)
            val2 = int(hash2, 16)
            return bin(val1 ^ val2).count("1")
        except (ValueError, TypeError):
            return 64

    # --------------------------------------------------------------------------
    # 2. Embedded Image Extraction from PDF and DOCX
    # --------------------------------------------------------------------------

    @classmethod
    def extract_images_from_pdf(cls, file_bytes: bytes) -> list[tuple[Image.Image, str]]:
        """Extracts all embedded raster images from a PDF document using PyMuPDF."""
        images: list[tuple[Image.Image, str]] = []
        if not PYMUPDF_AVAILABLE:
            return images

        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page_index in range(len(doc)):
                page = doc[page_index]
                image_list = page.get_images(full=True)
                for img_info in image_list:
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    img_bytes = base_image["image"]
                    ext = base_image.get("ext", "png").upper()
                    try:
                        pil_img = Image.open(io.BytesIO(img_bytes))
                        pil_img.load()
                        images.append((pil_img, ext))
                    except Exception:
                        continue
        except Exception:
            pass
        return images

    @classmethod
    def extract_images_from_docx(cls, file_bytes: bytes) -> list[tuple[Image.Image, str]]:
        """Extracts embedded raster images from a DOCX file by inspecting the word/media archive."""
        images: list[tuple[Image.Image, str]] = []
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as z:
                for filename in z.namelist():
                    if filename.startswith("word/media/"):
                        img_data = z.read(filename)
                        ext = filename.split(".")[-1].upper() if "." in filename else "PNG"
                        try:
                            pil_img = Image.open(io.BytesIO(img_data))
                            pil_img.load()
                            images.append((pil_img, ext))
                        except Exception:
                            continue
        except Exception:
            pass
        return images

    @classmethod
    def extract_images(cls, file_bytes: bytes, filename: str) -> list[tuple[Image.Image, str]]:
        """Unified extractor parsing PDF, DOCX, or direct raster images (PNG, JPEG, WebP)."""
        lower_name = filename.lower()
        if lower_name.endswith(".pdf") or file_bytes.startswith(b"%PDF"):
            return cls.extract_images_from_pdf(file_bytes)
        elif lower_name.endswith(".docx") or file_bytes.startswith(b"PK\x03\x04"):
            return cls.extract_images_from_docx(file_bytes)
        else:
            # Attempt direct image decode
            try:
                pil_img = Image.open(io.BytesIO(file_bytes))
                pil_img.load()
                fmt = (pil_img.format or "PNG").upper()
                return [(pil_img, fmt)]
            except Exception:
                return []

    # --------------------------------------------------------------------------
    # 3. Matching Against Approved Organizational Brand Assets Only
    # --------------------------------------------------------------------------

    @classmethod
    def evaluate_image(
        cls,
        image: Image.Image,
        image_index: int,
        source_format: str,
        approved_catalog: list[Any],
    ) -> AssetMatchFinding:
        """
        Evaluates a single extracted image against the organization's approved catalog.
        Flags:
        - APPROVED_MATCH: Correct approved logo within aspect ratio tolerance.
        - STRETCHED_OR_DISTORTED: Approved logo rendered with non-uniform scaling / distortion.
        - OUTDATED_LOGO: Matches an approved asset marked is_deprecated or expired.
        - UNAPPROVED_ASSET: Unrecognized brand graphic not matching any approved organizational asset.
        """
        now = datetime.now(timezone.utc)
        width, height = image.size
        embedded_ratio = round(width / max(1, height), 4)
        embedded_dhash = cls.compute_dhash(image)

        best_match = None
        min_distance = 65

        for asset in approved_catalog:
            asset_dhash = getattr(asset, "dhash", None) or (asset.get("dhash") if isinstance(asset, dict) else None)
            if not asset_dhash:
                continue

            dist = cls.hamming_distance(embedded_dhash, asset_dhash)
            if dist < min_distance:
                min_distance = dist
                best_match = asset

        # Check if match threshold met
        if best_match and min_distance <= cls.PERCEPTUAL_MATCH_THRESHOLD:
            # Resolved match in catalog
            if isinstance(best_match, dict):
                asset_id = best_match.get("id")
                asset_name = best_match.get("name", "Approved Asset")
                is_deprecated = bool(best_match.get("is_deprecated", False))
                valid_until = best_match.get("valid_until")
                approved_ratio = float(best_match.get("aspect_ratio", embedded_ratio))
            else:
                asset_id = getattr(best_match, "id", None)
                asset_name = getattr(best_match, "name", "Approved Asset")
                is_deprecated = bool(getattr(best_match, "is_deprecated", False))
                valid_until = getattr(best_match, "valid_until", None)
                approved_ratio = float(getattr(best_match, "aspect_ratio", embedded_ratio))

            # Confidence based on Hamming distance [0 -> 1.0, 12 -> 0.80]
            confidence = round(max(0.70, 1.0 - (min_distance / 40.0)), 3)

            # Check for Outdated / Deprecated logo
            is_expired = False
            if valid_until:
                if isinstance(valid_until, str):
                    try:
                        valid_until_dt = datetime.fromisoformat(valid_until)
                        is_expired = valid_until_dt < now
                    except Exception:
                        pass
                elif isinstance(valid_until, datetime):
                    is_expired = valid_until < now

            if is_deprecated or is_expired:
                return AssetMatchFinding(
                    embedded_image_index=image_index,
                    source_format=source_format,
                    embedded_aspect_ratio=embedded_ratio,
                    embedded_dhash=embedded_dhash,
                    match_status=AssetMatchStatus.OUTDATED_LOGO,
                    is_compliant=False,
                    confidence_score=confidence,
                    hamming_distance=min_distance,
                    aspect_ratio_distortion_percent=0.0,
                    matched_approved_asset_id=uuid.UUID(str(asset_id)) if asset_id else None,
                    matched_approved_asset_name=asset_name,
                    explanation=f"Outdated brand logo detected. Matches superseded asset '{asset_name}'. Must update to the current approved brand asset standard.",
                )

            # Check for Aspect Ratio Distortion / Stretched logo
            distortion_pct = round(abs(embedded_ratio - approved_ratio) / approved_ratio, 4)
            if distortion_pct > cls.ASPECT_RATIO_DISTORTION_TOLERANCE:
                distortion_display = round(distortion_pct * 100, 1)
                return AssetMatchFinding(
                    embedded_image_index=image_index,
                    source_format=source_format,
                    embedded_aspect_ratio=embedded_ratio,
                    embedded_dhash=embedded_dhash,
                    match_status=AssetMatchStatus.STRETCHED_OR_DISTORTED,
                    is_compliant=False,
                    confidence_score=confidence,
                    hamming_distance=min_distance,
                    aspect_ratio_distortion_percent=distortion_display,
                    matched_approved_asset_id=uuid.UUID(str(asset_id)) if asset_id else None,
                    matched_approved_asset_name=asset_name,
                    explanation=f"Distorted brand logo detected. Embedded image aspect ratio ({embedded_ratio}) deviates by {distortion_display}% from the approved {approved_ratio} standard for '{asset_name}'.",
                )

            # Valid compliant match
            return AssetMatchFinding(
                embedded_image_index=image_index,
                source_format=source_format,
                embedded_aspect_ratio=embedded_ratio,
                embedded_dhash=embedded_dhash,
                match_status=AssetMatchStatus.APPROVED_MATCH,
                is_compliant=True,
                confidence_score=confidence,
                hamming_distance=min_distance,
                aspect_ratio_distortion_percent=round(distortion_pct * 100, 1),
                matched_approved_asset_id=uuid.UUID(str(asset_id)) if asset_id else None,
                matched_approved_asset_name=asset_name,
                explanation=f"Verified compliant brand asset match with official catalog asset '{asset_name}'.",
            )

        # Unapproved / Unrecognized brand graphic
        return AssetMatchFinding(
            embedded_image_index=image_index,
            source_format=source_format,
            embedded_aspect_ratio=embedded_ratio,
            embedded_dhash=embedded_dhash,
            match_status=AssetMatchStatus.UNAPPROVED_ASSET,
            is_compliant=False,
            confidence_score=0.90,
            hamming_distance=min_distance if min_distance < 65 else None,
            aspect_ratio_distortion_percent=None,
            matched_approved_asset_id=None,
            matched_approved_asset_name=None,
            explanation="Unapproved visual asset. Image does not match any approved graphic in the organization's brand catalog.",
        )

    @classmethod
    def inspect_document(
        cls,
        file_bytes: bytes,
        filename: str,
        brand_profile_id: uuid.UUID,
        approved_catalog: list[Any],
    ) -> AssetCatalogMatchingResponse:
        """
        Extracts all embedded images from document and strictly verifies them
        against the organization's approved brand asset catalog.
        """
        extracted = cls.extract_images(file_bytes, filename)
        findings: list[AssetMatchFinding] = []

        compliant_cnt = 0
        unapproved_cnt = 0
        distorted_cnt = 0
        outdated_cnt = 0

        for idx, (img, fmt) in enumerate(extracted):
            finding = cls.evaluate_image(img, idx, fmt, approved_catalog)
            findings.append(finding)

            if finding.match_status == AssetMatchStatus.APPROVED_MATCH:
                compliant_cnt += 1
            elif finding.match_status == AssetMatchStatus.UNAPPROVED_ASSET:
                unapproved_cnt += 1
            elif finding.match_status == AssetMatchStatus.STRETCHED_OR_DISTORTED:
                distorted_cnt += 1
            elif finding.match_status == AssetMatchStatus.OUTDATED_LOGO:
                outdated_cnt += 1

        return AssetCatalogMatchingResponse(
            brand_profile_id=brand_profile_id,
            total_images_extracted=len(extracted),
            compliant_assets_count=compliant_cnt,
            unapproved_assets_count=unapproved_cnt,
            distorted_assets_count=distorted_cnt,
            outdated_assets_count=outdated_cnt,
            catalog_size_evaluated=len(approved_catalog),
            findings=findings,
            evaluated_at=datetime.now(timezone.utc),
        )
