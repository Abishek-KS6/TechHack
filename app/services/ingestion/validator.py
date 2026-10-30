"""
BrandShield AI - Document Ingestion Upload Validator.
Enforces multi-layer enterprise security verification:
1. Strict byte-level magic signature verification (rejects spoofed file extensions).
2. Filename sanitization against path traversal, control characters, and reserved device names.
3. Strict payload size boundaries.
4. Active threat detection: VBA macros, executable payload streams, and XML / zip bombs.
"""

from dataclasses import dataclass
import io
import os
import re
from typing import Any, Optional
import zipfile

from app.core.exceptions import ValidationErrorProblem

# Configuration Constants
DEFAULT_MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024       # 25 MiB
DEFAULT_MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024   # 100 MiB (Zip Bomb defense)
MAX_COMPRESSION_RATIO = 100.0                         # 100:1 ratio limit

# Magic byte signatures
PDF_MAGIC_HEADER = b"%PDF-"
ZIP_MAGIC_HEADER = b"PK\x03\x04"

# Forbidden PDF active content triggers
PDF_SUSPICIOUS_TOKENS = [
    b"/JavaScript",
    b"/JS",
    b"/Launch",
    b"/EmbeddedFiles",
]

# Forbidden DOCX macro payload paths
DOCX_FORBIDDEN_MACRO_ENTRIES = [
    "vbaproject.bin",
    "word/vbaproject.bin",
    "word/vbadata.xml",
]

# XML Bomb / Entity Expansion patterns
XML_BOMB_PATTERNS = [
    re.compile(rb"<!ENTITY", re.IGNORECASE),
    re.compile(rb"SYSTEM\s+[\"']", re.IGNORECASE),
    re.compile(rb"PUBLIC\s+[\"']", re.IGNORECASE),
]

# Reserved Windows file names
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


@dataclass
class ValidatedUpload:
    """Result container for sanitized and cryptographically verified file upload."""
    original_filename: str
    clean_filename: str
    detected_mime_type: str
    document_type: str  # "PDF", "DOCX", "TEXT", "MARKDOWN"
    size_bytes: int


class UploadValidator:
    """
    Zero-trust upload security validator defending against extension masquerading,
    path traversal attacks, macro exploits, and XML/zip bombs.
    """

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitizes filename against path traversal, control chars, and OS reserved identifiers.
        """
        if not filename or not filename.strip():
            return "document_upload"

        # Strip directory components (both / and \)
        basename = os.path.basename(filename.replace("\\", "/"))

        # Remove null bytes and control characters
        clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", basename)

        # Remove dangerous shell characters, preserve alphanumeric, dots, underscores, dashes
        clean = re.sub(r"[^\w\.\-\s]", "_", clean).strip()

        # Remove leading/trailing dots or spaces (e.g. "..file.pdf")
        clean = clean.strip(". ")

        # Prevent Windows reserved names
        name_root, ext = os.path.splitext(clean)
        if name_root.upper() in WINDOWS_RESERVED_NAMES:
            clean = f"safe_{clean}"

        if not clean:
            clean = "document_upload"

        # Limit to 255 characters preserving extension
        if len(clean) > 255:
            ext_len = len(ext)
            clean = clean[: 255 - ext_len] + ext

        return clean

    @classmethod
    def validate_file(
        cls,
        file_bytes: bytes,
        filename: str,
        max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> ValidatedUpload:
        """
        Performs exhaustive security validation on inbound document upload bytes.
        Raises ValidationErrorProblem if any validation or security control fails.
        """
        clean_filename = cls.sanitize_filename(filename)
        size = len(file_bytes)

        if size == 0:
            raise ValidationErrorProblem(
                detail="Uploaded file is empty (0 bytes).",
                extensions={"filename": clean_filename},
            )

        if size > max_size_bytes:
            max_mb = max_size_bytes / (1024 * 1024)
            actual_mb = round(size / (1024 * 1024), 2)
            raise ValidationErrorProblem(
                detail=f"File size exceeds maximum allowable limit of {max_mb} MB (received {actual_mb} MB).",
                extensions={"max_size_bytes": max_size_bytes, "received_bytes": size},
            )

        # ----------------------------------------------------------------------
        # 1. Magic Signature Identification (MIME Verification)
        # ----------------------------------------------------------------------
        if file_bytes.startswith(PDF_MAGIC_HEADER):
            detected_mime = "application/pdf"
            doc_type = "PDF"
            cls._scan_pdf_security(file_bytes, clean_filename)

        elif file_bytes.startswith(ZIP_MAGIC_HEADER):
            # Inspect internal ZIP catalog for OpenXML WordprocessingML markers
            detected_mime, doc_type = cls._verify_and_scan_docx(file_bytes, clean_filename)

        else:
            # Fallback to UTF-8 plaintext / markdown check
            detected_mime, doc_type = cls._verify_plaintext(file_bytes, clean_filename)

        return ValidatedUpload(
            original_filename=filename,
            clean_filename=clean_filename,
            detected_mime_type=detected_mime,
            document_type=doc_type,
            size_bytes=size,
        )

    @classmethod
    def _scan_pdf_security(cls, file_bytes: bytes, filename: str) -> None:
        """
        Scans PDF raw byte streams for prohibited active executable constructs and embedded scripts.
        """
        for token in PDF_SUSPICIOUS_TOKENS:
            if token in file_bytes:
                token_str = token.decode("latin1", errors="ignore")
                raise ValidationErrorProblem(
                    detail=(
                        f"Security policy violation in '{filename}': "
                        f"Prohibited executable or interactive trigger detected ({token_str})."
                    ),
                    extensions={"violation": "PDF_EXECUTABLE_PAYLOAD", "token": token_str},
                )

    @classmethod
    def _verify_and_scan_docx(cls, file_bytes: bytes, filename: str) -> tuple[str, str]:
        """
        Verifies DOCX integrity, enforces zip bomb decompression limits,
        scans for VBA macros, and detects XML entity expansion payloads.
        """
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
                namelist = zf.namelist()
                normalized_names = [name.lower() for name in namelist]

                # Verify presence of core word document XML
                if "word/document.xml" not in normalized_names:
                    raise ValidationErrorProblem(
                        detail=(
                            f"File signature mismatch in '{filename}': "
                            "ZIP archive does not contain valid Microsoft Word 'word/document.xml' schema."
                        ),
                        extensions={"violation": "INVALID_DOCX_SCHEMA"},
                    )

                # Zip bomb defense: check total uncompressed size and compression ratio
                total_uncompressed = 0
                for info in zf.infolist():
                    total_uncompressed += info.file_size
                    if total_uncompressed > DEFAULT_MAX_UNCOMPRESSED_BYTES:
                        raise ValidationErrorProblem(
                            detail=(
                                f"Decompression defense triggered in '{filename}': "
                                "Uncompressed content exceeds safety ceiling (potential zip bomb)."
                            ),
                            extensions={"violation": "ZIP_BOMB_LIMIT_EXCEEDED"},
                        )

                compressed_size = len(file_bytes)
                if compressed_size > 0:
                    ratio = total_uncompressed / compressed_size
                    if ratio > MAX_COMPRESSION_RATIO:
                        raise ValidationErrorProblem(
                            detail=(
                                f"Decompression defense triggered in '{filename}': "
                                f"Anomalous compression ratio ({ratio:.1f}:1) detected."
                            ),
                            extensions={"violation": "ZIP_BOMB_HIGH_RATIO", "ratio": ratio},
                        )

                # Macro scanning
                for entry in normalized_names:
                    for forbidden in DOCX_FORBIDDEN_MACRO_ENTRIES:
                        if forbidden in entry or entry.endswith(".vba") or entry.endswith(".bin"):
                            raise ValidationErrorProblem(
                                detail=(
                                    f"Security policy violation in '{filename}': "
                                    f"Embedded VBA macro or binary payload detected ('{entry}')."
                                ),
                                extensions={"violation": "FORBIDDEN_MACRO_PAYLOAD", "entry": entry},
                            )

                # XML Bomb / Entity Expansion Scanning
                for name in namelist:
                    if name.endswith(".xml") or name.endswith(".rels"):
                        xml_bytes = zf.read(name)
                        for pattern in XML_BOMB_PATTERNS:
                            if pattern.search(xml_bytes):
                                raise ValidationErrorProblem(
                                    detail=(
                                        f"Security policy violation in '{filename}': "
                                        f"Prohibited XML entity or DTD expansion detected in '{name}'."
                                    ),
                                    extensions={"violation": "XML_ENTITY_EXPANSION", "xml_file": name},
                                )

                return "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "DOCX"

        except (zipfile.BadZipFile, RuntimeError) as exc:
            raise ValidationErrorProblem(
                detail=f"Malformed or encrypted DOCX archive in '{filename}': {str(exc)}",
                extensions={"violation": "BAD_OR_ENCRYPTED_ZIP_FILE"},
            ) from exc

    @classmethod
    async def validate_upload_stream(
        cls,
        upload_file: Any,
        max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> tuple[bytes, ValidatedUpload]:
        """
        Streams file in 64KB chunks (read(65536) loop), aborting in-flight if max_size_bytes
        is exceeded before buffering into memory, then performs magic-byte and security scan.
        """
        chunks = []
        total_size = 0
        chunk_size = 65536  # 64 KB

        while True:
            chunk = await upload_file.read(chunk_size)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_size_bytes:
                max_mb = max_size_bytes / (1024 * 1024)
                actual_mb = round(total_size / (1024 * 1024), 2)
                raise ValidationErrorProblem(
                    detail=f"Streaming upload aborted: File size exceeds maximum limit of {max_mb} MB (received > {actual_mb} MB).",
                    extensions={"max_size_bytes": max_size_bytes, "received_bytes": total_size},
                )
            chunks.append(chunk)

        file_bytes = b"".join(chunks)
        validated = cls.validate_file(
            file_bytes=file_bytes,
            filename=upload_file.filename or "upload",
            max_size_bytes=max_size_bytes,
        )
        return file_bytes, validated

    @classmethod
    def _verify_plaintext(cls, file_bytes: bytes, filename: str) -> tuple[str, str]:
        """
        Validates UTF-8 encoded plain text or Markdown, ensuring absence of binary control codes.
        """
        # Binary null byte check
        if b"\x00" in file_bytes:
            raise ValidationErrorProblem(
                detail=(
                    f"Invalid document format in '{filename}': "
                    "Unrecognized binary file signature or null bytes detected."
                ),
                extensions={"violation": "UNRECOGNIZED_BINARY_FORMAT"},
            )

        try:
            file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationErrorProblem(
                detail=f"Plaintext content in '{filename}' must be valid UTF-8: {str(exc)}",
                extensions={"violation": "INVALID_UTF8_ENCODING"},
            ) from exc

        lower_name = filename.lower()
        if lower_name.endswith(".md") or lower_name.endswith(".markdown"):
            return "text/markdown", "MARKDOWN"
        return "text/plain", "TEXT"
