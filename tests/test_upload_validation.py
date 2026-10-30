"""
BrandShield AI - Upload Validator Security Test Suite.
Validates MIME signature verification, filename sanitization, macro scanning, and XML bomb defense.
"""

import io
import zipfile
import pytest

from app.core.exceptions import ValidationErrorProblem
from app.services.ingestion.validator import UploadValidator


def test_sanitize_filename_traversal_and_reserved_names():
    """Verifies path traversal removal and Windows reserved identifier protection."""
    # Path traversal POSIX
    assert UploadValidator.sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    # Path traversal Windows
    assert UploadValidator.sanitize_filename("..\\..\\Windows\\System32\\cmd.exe.docx") == "cmd.exe.docx"
    # Control characters and null bytes
    assert UploadValidator.sanitize_filename("clean\x00_name\x1f.pdf") == "clean_name.pdf"
    # Windows reserved name
    assert UploadValidator.sanitize_filename("CON.pdf").startswith("safe_")
    # Empty / whitespace fallback
    assert UploadValidator.sanitize_filename("   ...   ") == "document_upload"


def test_pdf_magic_byte_validation_success():
    """Verifies valid PDF magic byte header (%PDF-)."""
    valid_pdf = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    validated = UploadValidator.validate_file(valid_pdf, "quarterly_report.pdf")
    assert validated.document_type == "PDF"
    assert validated.detected_mime_type == "application/pdf"
    assert validated.clean_filename == "quarterly_report.pdf"


def test_spoofed_pdf_extension_rejected():
    """Verifies that plaintext renamed as .pdf is rejected if magic bytes do not match."""
    spoofed = b"This is just plain ASCII text masquerading as a PDF."
    # Since it lacks %PDF- and PK\x03\x04, validator falls back to plaintext check
    validated = UploadValidator.validate_file(spoofed, "malicious.pdf")
    assert validated.document_type == "TEXT"
    assert validated.detected_mime_type == "text/plain"


def test_pdf_javascript_and_executable_stream_blocked():
    """Verifies that PDF containing embedded /JavaScript or /Launch is blocked."""
    malicious_pdf = b"%PDF-1.7\n<< /Type /Action /S /JavaScript /JS (app.alert('PWNED')) >>\n%%EOF"
    with pytest.raises(ValidationErrorProblem) as exc_info:
        UploadValidator.validate_file(malicious_pdf, "exploit.pdf")
    assert exc_info.value.status_code == 422
    assert "Prohibited executable or interactive trigger" in exc_info.value.detail


def test_docx_magic_byte_and_schema_validation_success():
    """Verifies valid DOCX zip containing word/document.xml passes validation."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w:document><w:body></w:body></w:document>")
        zf.writestr("[Content_Types].xml", "<Types></Types>")

    valid_docx = buf.getvalue()
    validated = UploadValidator.validate_file(valid_docx, "brand_guidelines.docx")
    assert validated.document_type == "DOCX"
    assert validated.detected_mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_generic_zip_masquerading_as_docx_rejected():
    """Verifies that generic ZIP lacking word/document.xml is rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("notes.txt", "Some text file")

    fake_docx = buf.getvalue()
    with pytest.raises(ValidationErrorProblem) as exc_info:
        UploadValidator.validate_file(fake_docx, "fake.docx")
    assert exc_info.value.status_code == 422
    assert "does not contain valid Microsoft Word 'word/document.xml' schema" in exc_info.value.detail


def test_docx_vba_macro_payload_blocked():
    """Verifies that DOCX with embedded VBA macro file is blocked."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w:document><w:body></w:body></w:document>")
        zf.writestr("word/vbaProject.bin", b"\x00\x01\x02VBA_CODE")

    macro_docx = buf.getvalue()
    with pytest.raises(ValidationErrorProblem) as exc_info:
        UploadValidator.validate_file(macro_docx, "macro_infected.docx")
    assert exc_info.value.status_code == 422
    assert "Embedded VBA macro or binary payload detected" in exc_info.value.detail


def test_docx_xml_entity_expansion_bomb_blocked():
    """Verifies that XML containing billion-laughs <!ENTITY expansion is blocked."""
    evil_xml = """<?xml version="1.0"?>
    <!DOCTYPE lolz [
      <!ENTITY lol "lol">
      <!ENTITY lol2 "&lol;&lol;&lol;&lol;">
    ]>
    <w:document><w:body></w:body></w:document>
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", evil_xml)

    bomb_docx = buf.getvalue()
    with pytest.raises(ValidationErrorProblem) as exc_info:
        UploadValidator.validate_file(bomb_docx, "xml_bomb.docx")
    assert exc_info.value.status_code == 422
    assert "Prohibited XML entity or DTD expansion detected" in exc_info.value.detail


def test_file_size_exceeded_rejected():
    """Verifies that uploads exceeding max_size_bytes are rejected."""
    huge_data = b"A" * 1024
    with pytest.raises(ValidationErrorProblem) as exc_info:
        UploadValidator.validate_file(huge_data, "large.txt", max_size_bytes=512)
    assert exc_info.value.status_code == 422
    assert "File size exceeds maximum allowable limit" in exc_info.value.detail
