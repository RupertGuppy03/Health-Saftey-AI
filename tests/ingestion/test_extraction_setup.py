"""US-05 spike: prove the PDF extraction toolchain works.

Confirms the hybrid extraction setup produces usable output on a real WorkSafe
sample PDF, exercising the actual `src/ingestion/extract.py` functions rather
than the libraries directly:

  - PyMuPDF (fitz) for prose, via `extract_all_text`,
  - pdfplumber for tables, via `extract_tables`.

Paths come from `src.config.settings`, never hard-coded here.
"""

import fitz  # PyMuPDF
import pdfplumber
import pytest

from src.config import settings
from src.ingestion.extract import extract_all_text, extract_tables

# Known-good pages in the sample PDF (0-indexed), found by inspecting the doc:
#   page 7  -> continuous prose about PCBU duties,
#   page 31 -> a two-column shared-workplace checklist table.
# (Most "tables" in this guide are full-width styled callout boxes that detect
# as a single column; page 31 has genuine multi-column structure.)
PROSE_PAGE = 7
TABLE_PAGE = 31


@pytest.fixture(scope="module")
def sample_pdf():
    path = settings.SAMPLE_PDF
    assert path.exists(), f"Sample PDF not found at {path}"
    return path


def test_libraries_import():
    """AT1: both extraction libraries import with no dependency errors."""
    assert fitz.pymupdf_version
    assert pdfplumber.__version__


def test_pymupdf_extracts_prose(sample_pdf):
    """AT2: extraction returns a non-empty string of readable text on a prose page."""
    text = extract_all_text(sample_pdf)[PROSE_PAGE]

    assert isinstance(text, str)
    assert text.strip(), "prose page returned empty text"
    # Readable text has real words, not just symbols/whitespace.
    assert any(word.isalpha() and len(word) > 3 for word in text.split())


def test_pymupdf_extracts_all_pages(sample_pdf):
    """AT3: extraction returns text from every page, not just the first."""
    pages = extract_all_text(sample_pdf)

    assert len(pages) > 1, "document should have multiple pages"
    non_empty = [t for t in pages if t.strip()]
    # Most pages carry text, and not just page 1.
    assert len(non_empty) > 1
    assert pages[0].strip() != pages[PROSE_PAGE].strip(), (
        "later pages should differ from the first page"
    )


def test_pdfplumber_preserves_table_structure(sample_pdf):
    """AT4: extract_tables() keeps row/column structure on a table page."""
    tables = extract_tables(sample_pdf, TABLE_PAGE)

    assert tables, f"no table detected on page {TABLE_PAGE}"

    # Columns are preserved when a row keeps two or more separate, non-empty
    # cells rather than merging them into a single string.
    def has_separate_columns(table):
        return any(sum(1 for cell in row if cell and cell.strip()) > 1 for row in table)

    assert any(has_separate_columns(t) for t in tables), (
        "columns appear merged into single cells"
    )
