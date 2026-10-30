"""
BrandShield AI - Real Corporate PDF/DOCX Artifact Generator.
Generates 3 production-grade binary demonstration documents using PyMuPDF (fitz) and python-docx:
1. demo_artifacts/acme_q3_press_release.pdf (Multi-page PDF with layout coordinates, banned terms, expired facts, ungrounded claims, accessibility violations)
2. demo_artifacts/acme_partner_pitch.docx (Structured DOCX with tables, paragraphs, and active fact contradiction)
3. demo_artifacts/acme_compliant_memo.pdf (100% compliant corporate document for 0% false positive benchmarking)
"""

import os
from pathlib import Path
import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
import fitz  # PyMuPDF

OUTPUT_DIR = Path("demo_artifacts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_acme_q3_press_release_pdf() -> Path:
    """
    Generates multi-page PDF:
    - Page 1: Header, Banned terms ('100% risk-free', 'guaranteed monopoly'), Stale 2024 Fact ('$50M in assets under custody as of our 2023 annual filing').
    - Page 2: Ungrounded market share claim ('84.7% of the global institutional digital asset clearing market'), off-brand aggressive tone, 55-word accessibility run-on sentence.
    """
    pdf_path = OUTPUT_DIR / "acme_q3_press_release.pdf"
    doc = fitz.open()

    # --- Page 1 ---
    page1 = doc.new_page(width=595, height=842)  # A4 size

    # Header Banner
    page1.draw_rect(fitz.Rect(50, 40, 545, 90), color=(0.1, 0.2, 0.45), fill=(0.1, 0.2, 0.45))
    page1.insert_text(
        fitz.Point(65, 72),
        "ACME FINTECH GLOBAL - FOR IMMEDIATE RELEASE",
        fontsize=14,
        color=(1, 1, 1),
        fontname="helv",
    )

    # Title
    page1.insert_text(
        fitz.Point(50, 130),
        "Acme FinTech Unveils Q3 Global Liquidity Infrastructure",
        fontsize=16,
        color=(0.1, 0.1, 0.1),
        fontname="helv",
    )

    # Paragraph 1 (with Banned Superlatives)
    p1 = (
        "NEW YORK, NY -- Acme FinTech is thrilled to announce our next-generation enterprise "
        "clearing architecture. The platform delivers a 100% risk-free settlement environment "
        "establishing a guaranteed monopoly across modern interbank financial infrastructure. "
        "Our innovative algorithmic pipelines eliminate operational volatility entirely."
    )
    page1.insert_textbox(
        fitz.Rect(50, 150, 545, 230),
        p1,
        fontsize=10.5,
        color=(0.2, 0.2, 0.2),
        lineheight=1.4,
    )

    # Paragraph 2 (with Stale Temporal Fact: Expired 2024 Metric)
    p2 = (
        "Demonstrating consistent corporate traction, Acme FinTech maintains $50M in assets under custody "
        "as of our 2023 annual filing. Our global transaction pipeline continues to process institutional "
        "order volume with high velocity and deterministic ledger tracking across primary market counterparties."
    )
    page1.insert_textbox(
        fitz.Rect(50, 240, 545, 320),
        p2,
        fontsize=10.5,
        color=(0.2, 0.2, 0.2),
        lineheight=1.4,
    )

    # Footer Page 1
    page1.draw_line(fitz.Point(50, 800), fitz.Point(545, 800), color=(0.7, 0.7, 0.7), width=0.5)
    page1.insert_text(fitz.Point(50, 815), "Acme FinTech Global Inc. | Confidential Media Briefing", fontsize=8, color=(0.5, 0.5, 0.5))
    page1.insert_text(fitz.Point(500, 815), "Page 1 of 2", fontsize=8, color=(0.5, 0.5, 0.5))

    # --- Page 2 ---
    page2 = doc.new_page(width=595, height=842)

    # Header Page 2
    page2.insert_text(
        fitz.Point(50, 60),
        "Acme FinTech Q3 Commercial Disclosures (Continued)",
        fontsize=12,
        color=(0.1, 0.2, 0.45),
        fontname="helv",
    )
    page2.draw_line(fitz.Point(50, 75), fitz.Point(545, 75), color=(0.1, 0.2, 0.45), width=1)

    # Paragraph 3 (Ungrounded Claim / Needs Verification: 84.7% market share with no ground-truth fact)
    p3 = (
        "According to recent independent market research, Acme FinTech has captured 84.7% of the global "
        "institutional digital asset clearing market. This unprecedented adoption confirms our uncontested "
        "dominance across multi-asset collateral reconciliation networks worldwide."
    )
    page2.insert_textbox(
        fitz.Rect(50, 95, 545, 175),
        p3,
        fontsize=10.5,
        color=(0.2, 0.2, 0.2),
        lineheight=1.4,
    )

    # Paragraph 4 (Off-Brand Aggressive Tone + 55-word Readability Violation)
    p4 = (
        "Competitors are getting crushed and left in the dust by our crazy fast transaction engine. "
        "While conventional legacy infrastructure providers stumble through catastrophic outages and antiquated "
        "batch-processing workflows, our revolutionary autonomous routing matrix instantaneously and seamlessly "
        "orchestrates distributed multi-currency settlements without ever requiring manual intervention or intermediate reconciliation, "
        "delivering unmatched operational superiority that leaves every other legacy market participant completely hopeless."
    )
    page2.insert_textbox(
        fitz.Rect(50, 185, 545, 300),
        p4,
        fontsize=10.5,
        color=(0.2, 0.2, 0.2),
        lineheight=1.4,
    )

    # Mandatory disclaimer missing or partial
    page2.draw_line(fitz.Point(50, 800), fitz.Point(545, 800), color=(0.7, 0.7, 0.7), width=0.5)
    page2.insert_text(fitz.Point(50, 815), "Acme FinTech Global Inc. | Compliance & Regulatory Affairs", fontsize=8, color=(0.5, 0.5, 0.5))
    page2.insert_text(fitz.Point(500, 815), "Page 2 of 2", fontsize=8, color=(0.5, 0.5, 0.5))

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def generate_acme_partner_pitch_docx() -> Path:
    """
    Generates structured Microsoft Word DOCX:
    - Structured Headings and Body Paragraphs
    - Contains factual contradiction vs Active Fact:
      Active Fact: "Acme FinTech API responses maintain a 99th percentile processing time under 50 milliseconds for cached endpoints." (https://acmefintech.com/telemetry/p99-report.pdf)
      Pitch text claims: "Acme FinTech API responses maintain a 99th percentile processing time of 350 milliseconds for cached endpoints."
    - Structured Table with benchmark comparisons
    """
    docx_path = OUTPUT_DIR / "acme_partner_pitch.docx"
    doc = docx.Document()

    # Title
    title = doc.add_paragraph()
    r_title = title.add_run("Strategic Partner Briefing: Acme FinTech Enterprise Platform")
    r_title.bold = True
    r_title.font.size = Pt(20)
    r_title.font.color.rgb = RGBColor(25, 45, 100)

    # Subtitle
    sub = doc.add_paragraph()
    r_sub = sub.add_run("Confidential Institutional Partnership Proposal - Fiscal 2026")
    r_sub.italic = True
    r_sub.font.size = Pt(12)
    r_sub.font.color.rgb = RGBColor(100, 100, 100)

    # Heading 1
    doc.add_heading("1. Executive Architecture Overview", level=1)
    p1 = doc.add_paragraph(
        "Acme FinTech provides mission-critical liquidity infrastructure engineered for Tier-1 investment "
        "banks and liquidity providers. The platform enforces strict zero-trust role-based access control with "
        "Argon2id password hashing and cryptographic audit ledger verification."
    )
    p1.style = "Normal"

    # Heading 2: Telemetry Benchmarks with Factual Contradiction
    doc.add_heading("2. Production Telemetry & SLA Benchmarks", level=1)
    doc.add_paragraph(
        "Our telemetry logging infrastructure captures end-to-end distributed execution metrics across all "
        "active gateways."
    )

    # Contradicted figure against Active Fact:
    doc.add_paragraph(
        "Acme FinTech API responses maintain a 99th percentile processing time of 350 milliseconds for cached endpoints."
    )

    # Table with benchmark statistics
    doc.add_heading("3. Performance Matrix Summary", level=2)
    table = doc.add_table(rows=4, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    headers = ["Metric Identifier", "Specification Target", "Audit Verification Reference"]
    for i, h in enumerate(headers):
        cell = table.cell(0, i)
        cell.text = h
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.bold = True
            run.font.size = Pt(10)

    rows_data = [
        ("API P99 Latency (Cached)", "350 milliseconds", "Internal Engineering Telemetry"),
        ("Encryption Standard", "AES-256 GCM", "SOC 2 Type II Annex C"),
        ("Multi-Currency Clearing", "USD, EUR, GBP", "Product Settlement Specification"),
    ]

    for row_idx, row_data in enumerate(rows_data, start=1):
        for col_idx, text in enumerate(row_data):
            cell = table.cell(row_idx, col_idx)
            cell.text = text
            cell.paragraphs[0].runs[0].font.size = Pt(9.5)

    doc.add_paragraph()
    doc.add_paragraph(
        "Capital at risk. Past performance is not indicative of future results."
    )

    doc.save(str(docx_path))
    return docx_path


def generate_acme_compliant_memo_pdf() -> Path:
    """
    Generates 100% compliant corporate document:
    - Accurate trademark 'Acme FinTech™'
    - Cites verified active facts accurately
    - Includes mandatory regulatory disclaimers
    - Professional B2B executive tone, active voice, high readability
    - Used to prove 0% false positives on clean content
    """
    pdf_path = OUTPUT_DIR / "acme_compliant_memo.pdf"
    doc = fitz.open()

    page = doc.new_page(width=595, height=842)

    # Header
    page.draw_rect(fitz.Rect(50, 40, 545, 80), color=(0.1, 0.25, 0.4), fill=(0.1, 0.25, 0.4))
    page.insert_text(fitz.Point(65, 65), "ACME FINTECH GLOBAL - COMPLIANCE EXECUTIVE MEMORANDUM", fontsize=11, color=(1, 1, 1), fontname="helv")

    page.insert_text(fitz.Point(50, 115), "Enterprise Security & Infrastructure Status Report", fontsize=15, color=(0.1, 0.1, 0.1), fontname="helv")

    p1 = (
        "This memorandum provides an executive overview of our production security and regulatory posture. "
        "Acme FinTech™ infrastructure is certified compliant with SOC 2 Type II and ISO 27001 standards. "
        "Our engineering teams maintain continuous control monitoring to protect institutional client assets."
    )
    page.insert_textbox(fitz.Rect(50, 135, 545, 210), p1, fontsize=10.5, color=(0.2, 0.2, 0.2), lineheight=1.4)

    p2 = (
        "All client data at rest is encrypted using AES-256 and audit trails are recorded in a SHA-256 "
        "tamper-evident ledger. The platform enforces strict zero-trust role-based access control with "
        "Argon2id password hashing to safeguard institutional account credentials against credential stuffing attacks."
    )
    page.insert_textbox(fitz.Rect(50, 220, 545, 295), p2, fontsize=10.5, color=(0.2, 0.2, 0.2), lineheight=1.4)

    p3 = (
        "Acme FinTech™ supports multi-currency settlement in USD, EUR, and GBP for verified enterprise accounts. "
        "Acme FinTech operates secondary redundant data centers across two distinct geographical regions to maintain "
        "uninterrupted settlement services during scheduled maintenance windows."
    )
    page.insert_textbox(fitz.Rect(50, 305, 545, 380), p3, fontsize=10.5, color=(0.2, 0.2, 0.2), lineheight=1.4)

    # Regulatory Disclaimer
    page.draw_rect(fitz.Rect(50, 400, 545, 450), color=(0.9, 0.9, 0.9), fill=(0.96, 0.96, 0.96))
    p_disc = "Capital at risk. Past performance is not indicative of future results. Investments are subject to market risk."
    page.insert_textbox(fitz.Rect(60, 412, 535, 440), p_disc, fontsize=9.5, color=(0.3, 0.3, 0.3), fontname="helv")

    # Footer
    page.draw_line(fitz.Point(50, 800), fitz.Point(545, 800), color=(0.7, 0.7, 0.7), width=0.5)
    page.insert_text(fitz.Point(50, 815), "Acme FinTech Global Inc. | Approved Regulatory Communication", fontsize=8, color=(0.5, 0.5, 0.5))

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def main():
    print("Generating corporate demonstration artifacts in demo_artifacts/...")
    p1 = generate_acme_q3_press_release_pdf()
    print(f"  [OK] Created Multi-Page PDF: {p1} ({os.path.getsize(p1)} bytes)")

    p2 = generate_acme_partner_pitch_docx()
    print(f"  [OK] Created Structured DOCX: {p2} ({os.path.getsize(p2)} bytes)")

    p3 = generate_acme_compliant_memo_pdf()
    print(f"  [OK] Created Compliant PDF: {p3} ({os.path.getsize(p3)} bytes)")

    print("All 3 demonstration artifacts generated successfully.")


if __name__ == "__main__":
    main()
