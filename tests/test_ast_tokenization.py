"""
BrandShield AI - Offset-Preserving AST Tokenization Test Suite.
Validates Unicode NFC normalization, character offset fidelity (raw_text[start:end] == span.text),
PDF bounding boxes, and DOCX styles/tables.
"""

import io
import zipfile
import fitz

from app.services.ingestion.parser import OffsetPreservingASTParser


def test_text_parsing_offset_fidelity_and_unicode_nfc():
    """
    Validates that text parsing segments into paragraphs and sentences,
    normalizes Unicode to NFC, and maintains exact mathematical offset alignment.
    """
    # Decomposed Unicode (e + acute accent \u0301)
    decomposed = "Cafe\u0301 enterprise brand guidelines.\n\nOur market share grew 15% in Q3. Compliance is required."
    parsed = OffsetPreservingASTParser.parse_text(decomposed, document_type="TEXT")

    assert parsed.document_type == "TEXT"
    assert parsed.total_spans >= 3
    # Check NFC normalization (é combined)
    assert "Café" in parsed.raw_text

    # Strict mathematical invariant: raw_text[start:end] == span.text
    for span in parsed.ast_span_map:
        extracted = parsed.raw_text[span["start_char"] : span["end_char"]]
        assert extracted == span["text"]
        assert len(extracted) > 0


def test_pdf_parsing_bounding_boxes_and_page_indices():
    """
    Creates an in-memory PDF using PyMuPDF and validates that:
    1. Blocks have valid [x0, y0, x1, y1] coordinates.
    2. Page numbers (1-indexed) are accurately assigned.
    3. Global character offsets strictly equal the span text.
    """
    doc = fitz.open()
    # Page 1
    p1 = doc.new_page()
    p1.insert_text((72, 100), "BrandShield Enterprise AI Platform.")
    p1.insert_text((72, 150), "Zero-trust regulatory boundary verified.")
    # Page 2
    p2 = doc.new_page()
    p2.insert_text((72, 100), "Page two appendix and disclosures.")
    pdf_bytes = doc.tobytes()
    doc.close()

    parsed = OffsetPreservingASTParser.parse_pdf(pdf_bytes)

    assert parsed.document_type == "PDF"
    assert parsed.metadata["page_count"] == 2
    assert len(parsed.ast_span_map) >= 3

    # Validate bounding boxes and page numbers
    page_numbers = {s.get("page_number") for s in parsed.ast_span_map if "page_number" in s}
    assert 1 in page_numbers
    assert 2 in page_numbers

    for span in parsed.ast_span_map:
        if span["node_type"] == "pdf_block":
            bbox = span.get("bbox")
            assert bbox is not None
            assert len(bbox) == 4
            assert bbox[0] < bbox[2]  # x0 < x1
            assert bbox[1] < bbox[3]  # y0 < y1

        # Strict mathematical invariant
        extracted = parsed.raw_text[span["start_char"] : span["end_char"]]
        assert extracted == span["text"]


def test_docx_parsing_styles_and_table_cells():
    """
    Creates an in-memory DOCX archive and validates that:
    1. Paragraph styles (e.g. Heading1) are preserved.
    2. Tables and cells preserve table/row/col indices.
    3. Global character offsets strictly equal the span text.
    """
    doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
          <w:r><w:t>Brand Identity Framework</w:t></w:r>
        </w:p>
        <w:p>
          <w:pPr><w:pStyle w:val="Normal"/></w:pPr>
          <w:r><w:t>All marketing copy must avoid speculative medical claims.</w:t></w:r>
        </w:p>
        <w:tbl>
          <w:tr>
            <w:tc><w:p><w:r><w:t>Guideline ID</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>Enforcement Level</w:t></w:r></w:p></w:tc>
          </w:tr>
          <w:tr>
            <w:tc><w:p><w:r><w:t>SEC-CL-01</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>CRITICAL</w:t></w:r></w:p></w:tc>
          </w:tr>
        </w:tbl>
      </w:body>
    </w:document>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
        zf.writestr("[Content_Types].xml", "<Types></Types>")

    docx_bytes = buf.getvalue()
    parsed = OffsetPreservingASTParser.parse_docx(docx_bytes)

    assert parsed.document_type == "DOCX"
    assert parsed.metadata["table_count"] >= 1

    # Verify heading and paragraph styles
    headings = [s for s in parsed.ast_span_map if s.get("style") == "Heading1"]
    assert len(headings) >= 1
    assert headings[0]["text"] == "Brand Identity Framework"

    # Verify table cells
    cells = [s for s in parsed.ast_span_map if s["node_type"] == "table_cell"]
    assert len(cells) == 4
    cell_texts = [c["text"] for c in cells]
    assert "Guideline ID" in cell_texts
    assert "CRITICAL" in cell_texts

    # Strict mathematical invariant
    for span in parsed.ast_span_map:
        extracted = parsed.raw_text[span["start_char"] : span["end_char"]]
        assert extracted == span["text"]
