"""PDF text extraction — the hybrid setup for the Health & Safety pipeline.

PyMuPDF (fitz) for prose, pdfplumber for tables. This is the US-05 *setup*:
the goal here is simply to pull ALL the text out of a document so we can confirm
extraction works end to end. Cleaning it up (headers/footers, hyphenation) and
preserving table structure properly come later, in US-06 and US-07.

Run it to dump the full extracted text of the sample PDF:

    .venv/bin/python -m src.ingestion.extract

Paths come from `src.config.settings`; nothing is hard-coded here.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber

from src.config import settings

# A page known to contain a table, used only to show pdfplumber is wired up.
TABLE_PAGE = 31


def extract_all_text(pdf_path: Path) -> list[str]:
    """Extract text from every page with PyMuPDF, one string per page.

    Page-by-page (not the whole document at once) so page numbers can be
    attached as metadata later in the pipeline.
    """
    pages: list[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for page_index in range(doc.page_count):
            pages.append(str(doc[page_index].get_text()))
    return pages


def extract_tables(pdf_path: Path, page_number: int) -> list:
    """Extract tables from one page with pdfplumber (the table half of the hybrid)."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        return pdf.pages[page_number].extract_tables()


def main():
    """Dump the full extracted text of the sample PDF for visual inspection."""
    pdf_path = settings.SAMPLE_PDF
    pages = extract_all_text(pdf_path)
    total_chars = sum(len(text) for text in pages)

    print(f"Source: {pdf_path.name}")
    print(f"Pages: {len(pages)}  |  Total characters: {total_chars}\n")

    for page_index, text in enumerate(pages):
        print("=" * 78)
        print(f"PAGE {page_index}  ({len(text.strip())} chars)")
        print("=" * 78)
        print(text.strip() or "[no extractable text on this page — possible image-only page]")
        print()

    # Show the table half of the hybrid setup is working too.
    print("#" * 78)
    print(f"# pdfplumber tables on page {TABLE_PAGE} (raw)")
    print("#" * 78)
    for table in extract_tables(pdf_path, TABLE_PAGE):
        for row in table:
            print(row)
        print()


if __name__ == "__main__":
    main()
