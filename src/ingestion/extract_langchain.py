"""PDF text extraction via LangChain's PyMuPDFLoader — a US-05 comparison spike.

The current extractor (`src.ingestion.extract`) returns a bare `list[str]`, one
string per page, with page numbers only implied by list index. This variant uses
LangChain's `PyMuPDFLoader`, which returns `Document` objects that carry the text
(`page_content`) *and* a `metadata` dict (source, page, total_pages, PDF metadata)
glued together — the native shape the downstream LangChain splitter and Chroma
consume. The point of this file is to produce that output side by side with the
current extractor so we can eyeball whether it's an improvement.

Scope notes:
  * Prose only. Tables are deferred to US-07; this file does not touch them.
  * Figure-caption / header-footer cleaning is a US-06 concern, not done here.
  * `PyMuPDFLoader` hands back a flat string per page, so the positional block
    data (font size / bounding boxes from `get_text("dict")`) that figure and
    header/footer cleaning would rely on is NOT available from this path.

Run it to dump the loader output for the sample PDF and compare page/char counts
against the current extractor:

    .venv/bin/python -m src.ingestion.extract_langchain

The document is `settings.SAMPLE_PDF` (PCBUs-Working-Together-GPG.pdf); nothing is
hard-coded here.
"""

from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document

from src.config import settings
from src.ingestion.extract import extract_all_text


def extract_documents(pdf_path: Path) -> list[Document]:
    """Extract one LangChain `Document` per page via PyMuPDFLoader.

    Each Document holds the page text in `page_content` and page metadata
    (source, page, total_pages, plus the PDF's own metadata) in `metadata`.
    """
    return PyMuPDFLoader(str(pdf_path)).load()


def main():
    """Dump the loader output for the sample PDF and compare to `extract.py`."""
    pdf_path = settings.SAMPLE_PDF
    docs = extract_documents(pdf_path)
    total_chars = sum(len(doc.page_content) for doc in docs)

    print(f"Source: {pdf_path.name}")
    print(f"Pages: {len(docs)}  |  Total characters: {total_chars}\n")

    for page_index, doc in enumerate(docs):
        text = doc.page_content
        print("=" * 78)
        print(f"PAGE {page_index}  ({len(text.strip())} chars)")
        print(f"metadata: {doc.metadata}")
        print("=" * 78)
        print(text.strip() or "[no extractable text on this page — possible image-only page]")
        print()

    # Side-by-side comparison against the current list[str] extractor. Same
    # underlying fitz engine, so page count should match and total chars be equal
    # or very close — this is the "is there an improvement?" eyeball test.
    string_pages = extract_all_text(pdf_path)
    string_chars = sum(len(text) for text in string_pages)

    print("#" * 78)
    print("# Comparison: PyMuPDFLoader (Documents)  vs  extract_all_text (list[str])")
    print("#" * 78)
    print(f"{'':22}{'PyMuPDFLoader':>16}{'extract_all_text':>20}")
    print(f"{'pages':22}{len(docs):>16}{len(string_pages):>20}")
    print(f"{'total characters':22}{total_chars:>16}{string_chars:>20}")


if __name__ == "__main__":
    main()
