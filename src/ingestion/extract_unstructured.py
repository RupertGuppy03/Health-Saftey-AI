"""Unstructured.io cleaning spike — a US-06 TEST on a single document.

Evaluates whether Unstructured's hosted Transform API returns clean, chunk-ready
text in one step. Unstructured partitions a PDF into typed *elements* (Title,
NarrativeText, Header, Footer, PageNumber, FigureCaption, Image, Table, ...), each
with metadata (page_number, coordinates). That turns cleaning into a *filter by
element type* — drop Header/Footer/PageNumber/Image — instead of regex, and the
kept elements convert straight into langchain `Document`s for chunking.

TESTING ONLY (do not adopt until the output is confirmed clean):
  * Runs on `settings.SAMPLE_PDF` (PCBUs-Working-Together-GPG.pdf) only.
  * `unstructured-client` is installed into .venv locally and is NOT pinned in
    requirements.txt. README / docs are intentionally untouched.
  * The API key is read from the environment (`UNSTRUCTURED_API_KEY` in .env, which
    is gitignored) — never hard-coded, never committed.

If the Transform UI's "generate code" button emits a different request shape for
your workflow, reconcile `extract_elements` with it — this uses the documented SDK
pattern for unstructured-client 0.45.0.

Run:

    .venv/bin/python -m src.ingestion.extract_unstructured
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from unstructured_client import UnstructuredClient
from unstructured_client.models import operations, shared

from src.config import settings

load_dotenv()

# The SDK's general.partition() targets the Serverless Partition API, whose path
# (/general/v0/general) only exists on api.unstructuredapp.io. The Transform host
# (platform-api.transform.unstructured.io) is a different product and 404s here.
# Overridable via .env (UNSTRUCTURED_API_URL) if the key is scoped elsewhere.
SERVER_URL = os.environ.get(
    "UNSTRUCTURED_API_URL", "https://api.unstructuredapp.io"
)

# Element types that are noise for retrieval — the "cleaning" is dropping these.
DROP_TYPES = {"Header", "Footer", "PageNumber", "Image"}


def extract_elements(pdf_path: Path) -> list[dict]:
    """Partition a PDF into Unstructured elements via the hosted Transform API.

    Returns the raw element dicts (element_id, text, type, metadata). Uses the
    hi_res strategy (best for layout + tables) and asks for table structure so
    Table elements come back with `metadata.text_as_html`.
    """
    api_key = os.environ.get("UNSTRUCTURED_API_KEY")
    if not api_key:
        raise RuntimeError(
            "UNSTRUCTURED_API_KEY is not set. Add it to .env (which is gitignored)."
        )

    client = UnstructuredClient(api_key_auth=api_key, server_url=SERVER_URL)

    req = operations.PartitionRequest(
        partition_parameters=shared.PartitionParameters(
            files=shared.Files(content=pdf_path.read_bytes(), file_name=pdf_path.name),
            strategy=shared.Strategy.HI_RES,
            pdf_infer_table_structure=True,
        )
    )
    return client.general.partition(request=req).elements or []


def to_clean_documents(elements: list[dict]) -> list[Document]:
    """Drop noise elements and group the rest into one langchain Document per page.

    Cleaning = filter out DROP_TYPES. The surviving text is joined per page so the
    output mirrors the page model of the other extractors and is ready for a
    langchain splitter to chunk. Page number rides along in metadata.
    """
    pages: dict[int, list[str]] = {}
    for el in elements:
        if el.get("type") in DROP_TYPES:
            continue
        text = (el.get("text") or "").strip()
        if not text:
            continue
        page = el.get("metadata", {}).get("page_number", 0)
        pages.setdefault(page, []).append(text)

    return [
        Document(
            page_content="\n\n".join(chunks),
            metadata={"source": settings.SAMPLE_PDF.name, "page": page},
        )
        for page, chunks in sorted(pages.items())
    ]


def main():
    """Run the spike on the sample PDF and print what to eyeball for the gate."""
    pdf_path = settings.SAMPLE_PDF
    print(f"Source: {pdf_path.name}")
    print("Calling Unstructured (hi_res)… this is slower than local fitz.\n")

    elements = extract_elements(pdf_path)

    # 1. Type counts — did it detect Header/Footer/PageNumber so we can drop them?
    counts = Counter(el.get("type") for el in elements)
    print("Element type counts:")
    for etype, n in counts.most_common():
        flag = "  <- dropped" if etype in DROP_TYPES else ""
        print(f"  {etype:20} {n:>4}{flag}")

    # 2. The cleaned, page-grouped Documents ready for chunking.
    docs = to_clean_documents(elements)
    clean_chars = sum(len(d.page_content) for d in docs)
    print(f"\nClean Documents: {len(docs)} pages, {clean_chars} characters total\n")
    for doc in docs:
        print("=" * 78)
        print(f"PAGE {doc.metadata['page']}  ({len(doc.page_content)} chars)")
        print("=" * 78)
        print(doc.page_content or "[empty after cleaning]")
        print()

    # 3. Confirm tables came back with structure (text_as_html).
    print("#" * 78)
    print("# First Table element as HTML (US-07 preview)")
    print("#" * 78)
    tables = [el for el in elements if el.get("type") == "Table"]
    if tables:
        print(tables[0].get("metadata", {}).get("text_as_html", "[no text_as_html]"))
    else:
        print("[no Table elements detected]")


if __name__ == "__main__":
    main()
