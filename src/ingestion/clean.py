"""Deterministic cleaning of Unstructured.io JSON output.

STATUS: spike / proposal. The move from the locked hybrid PyMuPDF+pdfplumber
pipeline to Unstructured is paused pending team sign-off, so this does NOT
rewrite any user story. It only demonstrates that, given the *cached* JSON,
cleaning is fully reproducible.

Why this is reproducible: the Unstructured API is non-deterministic and paid, so
the committed JSON is treated as the source of truth. This module makes NO API
call and adds NO new dependency — it is pure stdlib on top of that JSON.

Pipeline (all deterministic):
  1. Keep only useful element types (drops headers/footers/page numbers/images).
  2. Remove boilerplate by content (ToC, cover, ISBN, disclaimer) — never by page.
  3. Normalise text generically (Unicode NFKC for ligatures + safe glyph fixes).
  4. Render tables from `metadata.text_as_html` (structure preserved), not the
     flattened `text`.
  5. Emit one cleaned record per element with metadata aligned to the locked
     US-09 schema (source_file, page_number, section_heading, chunk_type) so it
     hands off cleanly to the chunking step (Luca / US-08-09).

Run:  .venv/bin/python -m src.ingestion.clean
"""

from __future__ import annotations

import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

from src.config import settings

# Element types worth keeping; everything else (Header, Footer, PageNumber,
# Image, UncategorizedText, Form) is boilerplate we drop by type.
KEEP_TYPES = {"NarrativeText", "Title", "ListItem", "Table"}

# The cached Unstructured JSON for the sample document lives here.
SAMPLE_JSON_DIR = settings.DATA_PROCESSED_DIR / "pcbus_working_together"

# Phrases that mark WorkSafe front/back-matter boilerplate. Matched case-
# insensitively as substrings, so they generalise across the WorkSafe corpus
# rather than being tied to one document's page numbers.
BOILERPLATE_PHRASES = (
    "acknowledgements",
    "would like to acknowledge",
    "this publication provides general guidance",
    "creative commons",
    "copyright work is licensed",
    "to view a copy of this licence",
    "you are free to copy",
    "po box",
    "worksafe.govt.nz",
    "published:",
    "about worksafe",
)

# ISBN lines, e.g. "ISBN: 978-1-98-856734-1 (online)".
ISBN_RE = re.compile(r"\bisbn\b|\b97[89][\s-]", re.IGNORECASE)

# The "CONTENTS" heading marks the start of the front-matter table of contents.
# Only "contents" is used as the skip trigger — "appendices"/"tables"/"figures"
# also name REAL back-matter sections we must keep, so they are NOT triggers.
TOC_HEADINGS = {"contents"}

# Obvious ligature-glyph misreads from the VLM that Unicode NFKC can't fix.
# These are whole broken tokens that are not real words, so replacing them is
# safe. Kept small and generic; anything else suspicious is FLAGGED, not patched.
GLYPH_ARTIFACTS = {
    "di(erent": "different",
    "e0cient": "efficient",
    "e0ciency": "efficiency",
    "tra0c": "traffic",
    "o0cer": "officer",
    "o0cers": "officers",
}

# A "word" that still looks broken after normalisation (a bracket or digit
# wedged inside letters), so we can report residual extraction damage.
SUSPICIOUS_TOKEN_RE = re.compile(r"[A-Za-z]+[(0-9)][A-Za-z]+")


# --------------------------------------------------------------------------- #
# Text normalisation
# --------------------------------------------------------------------------- #
def normalise_text(text: str) -> str:
    """Generic, document-agnostic text cleanup."""
    # NFKC folds ligatures (ﬁ->fi, ﬂ->fl, ﬀ->ff) and other compatibility forms.
    text = unicodedata.normalize("NFKC", text)
    for broken, fixed in GLYPH_ARTIFACTS.items():
        text = text.replace(broken, fixed)
    # Collapse runs of whitespace/newlines into single spaces.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_suspicious_tokens(text: str) -> list[str]:
    """Residual glyph damage we did NOT auto-fix — reported, never silently kept."""
    return SUSPICIOUS_TOKEN_RE.findall(text)


# --------------------------------------------------------------------------- #
# HTML table -> Markdown (keeps rows/columns)
# --------------------------------------------------------------------------- #
class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def html_table_to_markdown(html: str) -> str:
    """Convert a simple HTML table to a Markdown table, padding ragged rows."""
    parser = _TableParser()
    parser.feed(html)
    rows = [[normalise_text(cell) for cell in row] for row in parser.rows if row]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |",
             "| " + " | ".join(["---"] * width) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Boilerplate detection (by content, never by page number)
# --------------------------------------------------------------------------- #
def is_boilerplate(text: str) -> bool:
    lowered = text.lower()
    if ISBN_RE.search(text):
        return True
    return any(phrase in lowered for phrase in BOILERPLATE_PHRASES)


# --------------------------------------------------------------------------- #
# chunk_type / section tracking
# --------------------------------------------------------------------------- #
def classify_chunk_type(element_type: str, section_heading: str) -> str:
    """One of the locked US-09 values: prose | table | appendix | glossary."""
    heading = section_heading.lower()
    if "glossary" in heading:
        return "glossary"
    if "appendix" in heading:
        return "appendix"
    if element_type == "Table":
        return "table"
    return "prose"


# --------------------------------------------------------------------------- #
# Main cleaning pass
# --------------------------------------------------------------------------- #
def _looks_like_body_paragraph(element_type: str, text: str) -> bool:
    """True for a real body paragraph — used to end the table-of-contents skip.

    Index/heading lines start with a digit or are short fragments; a genuine
    paragraph is a longer sentence that starts with a letter and ends in
    sentence punctuation.
    """
    return (
        element_type == "NarrativeText"
        and len(text) > 120
        and text[:1].isalpha()
        and text.rstrip().endswith((".", ":"))
    )


def clean_elements(elements: list[dict], source_file: str) -> dict:
    """Return {"records": [...], "report": {...}} from raw Unstructured elements."""
    records: list[dict] = []
    dropped_by_type = 0
    dropped_boilerplate = 0
    suspicious: list[str] = []
    skipping_toc = False
    section_heading = ""

    for el in elements:
        el_type = el.get("type", "")
        meta = el.get("metadata", {})

        if el_type not in KEEP_TYPES:
            dropped_by_type += 1
            continue

        raw = el.get("text", "") or ""

        # Normalise FIRST, then detect — so ligatures (e.g. "ﬁgures") can't slip a
        # ToC/index heading past the filters.
        if el_type == "Table":
            html = meta.get("text_as_html", "")
            text = html_table_to_markdown(html) if html else normalise_text(raw)
        else:
            text = normalise_text(raw)

        if not text:
            continue

        # Table of contents: the "CONTENTS" heading starts a skip that runs until
        # the first real body paragraph. This swallows the section list and the
        # list-of-tables/figures indexes in one go, without touching the real
        # appendices at the back of the document.
        if el_type != "Table" and text.lower() in TOC_HEADINGS:
            skipping_toc = True
            dropped_boilerplate += 1
            continue
        if skipping_toc:
            if _looks_like_body_paragraph(el_type, text):
                skipping_toc = False  # body has resumed; keep this element
            else:
                dropped_boilerplate += 1
                continue

        if el_type != "Table" and is_boilerplate(text):
            dropped_boilerplate += 1
            continue

        # Track the current section heading (last real Title seen).
        if el_type == "Title":
            section_heading = text

        suspicious.extend(find_suspicious_tokens(text))

        records.append({
            "text": text,
            "source_file": source_file,
            "page_number": meta.get("page_number"),
            "element_type": el_type,
            "section_heading": section_heading,
            "chunk_type": classify_chunk_type(el_type, section_heading),
        })

    report = {
        "kept": len(records),
        "dropped_by_type": dropped_by_type,
        "dropped_boilerplate": dropped_boilerplate,
        "suspicious_tokens": sorted(set(suspicious)),
    }
    return {"records": records, "report": report}


def _find_cached_json() -> Path:
    matches = sorted(SAMPLE_JSON_DIR.glob("*.pdf.json"))
    if not matches:
        raise FileNotFoundError(f"No cached Unstructured JSON in {SAMPLE_JSON_DIR}")
    return matches[0]


def main():
    json_path = _find_cached_json()
    elements = json.loads(json_path.read_text())

    # Prefer the original filename recorded by Unstructured; fall back to the PDF.
    source_file = ""
    for el in elements:
        source_file = el.get("metadata", {}).get("filename", "")
        if source_file:
            break
    source_file = source_file or settings.SAMPLE_PDF.name

    result = clean_elements(elements, source_file)
    records, report = result["records"], result["report"]

    # Write cleaned JSON (the handoff artifact for chunking).
    out_json = SAMPLE_JSON_DIR / "PCBUs-Working-Together-CLEANED.json"
    out_json.write_text(json.dumps(records, indent=2, ensure_ascii=False))

    # Write a readable preview.
    out_txt = SAMPLE_JSON_DIR / "PCBUs-Working-Together-CLEANED-preview.txt"
    preview = "\n\n".join(
        f"[p{r['page_number']} | {r['chunk_type']} | {r['section_heading']}]\n{r['text']}"
        for r in records
    )
    out_txt.write_text(preview)

    print(f"Source JSON : {json_path.name}")
    print(f"Source file : {source_file}")
    print(f"Kept records: {report['kept']}")
    print(f"Dropped (by type)      : {report['dropped_by_type']}")
    print(f"Dropped (boilerplate)  : {report['dropped_boilerplate']}")
    print(f"Suspicious tokens left : {report['suspicious_tokens']}")
    print(f"\nWrote: {out_json}")
    print(f"Wrote: {out_txt}")


if __name__ == "__main__":
    main()
