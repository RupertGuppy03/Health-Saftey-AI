"""Contract tests for the cleaned corpus (src/ingestion/clean.py).

These run against the committed cleaned output in `data/processed/` rather than
the raw Unstructured JSON, which was removed from the repo in commit b1ccecf.
No API call is made.

Two kinds of test live here:

* Corpus contract tests read PCBUs-Working-Together-CLEANED.json and assert the
  US-07/US-09 guarantees the Sprint 2 embedding step depends on. They check the
  data on disk, so they catch a corrupted or stale corpus but not a regression
  in clean.py itself.
* Unit tests below build raw-shaped elements inline and run the cleaning
  functions directly, so clean.py keeps real coverage without needing the
  3.5 MB raw JSON back in the repo.
"""

import json

import pytest

from src.config import settings
from src.ingestion import clean

ALLOWED_CHUNK_TYPES = {"prose", "table", "appendix", "glossary"}

CLEANED_JSON = (
    settings.DATA_PROCESSED_DIR
    / "pcbus_working_together"
    / "PCBUs-Working-Together-CLEANED.json"
)

SOURCE_FILE = "PCBUs-Working-Together-GPG-7fcb7c71.pdf"


@pytest.fixture(scope="module")
def records():
    if not CLEANED_JSON.exists():
        pytest.skip(f"cleaned corpus not present: {CLEANED_JSON}")

    return json.loads(CLEANED_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def blob(records):
    return "\n".join(r["text"] for r in records)


# =====================================================
# CORPUS CONTRACT
# =====================================================

def test_boilerplate_removed(blob):
    """No ISBN / copyright / disclaimer boilerplate survives cleaning."""
    lowered = blob.lower()
    assert "978-1-98" not in lowered
    assert "creative commons" not in lowered
    assert "this publication provides general guidance" not in lowered


def test_dropped_element_types_absent(records):
    """Headers/footers/page-numbers/images are gone (kept types only)."""
    assert all(r["element_type"] in clean.KEEP_TYPES for r in records)


def test_glossary_table_keeps_term_and_definition(records):
    """The glossary row pdfplumber lost — TERM paired with its definition — survives."""
    paired = [
        r for r in records
        if "Contractor" in r["text"] and "carries out temporary" in r["text"]
    ]
    assert paired, "glossary term 'Contractor' not paired with its definition"


def test_ligatures_normalised(blob):
    """Generic NFKC + glyph fixes remove the broken 'di(erent' style tokens."""
    assert "di(erent" not in blob
    assert "ﬁ" not in blob and "ﬂ" not in blob


def test_every_record_has_locked_metadata(records):
    """US-09 schema: source_file, page_number, section_heading, chunk_type present."""
    assert records, "no records produced"
    for r in records:
        assert r["source_file"] == SOURCE_FILE
        assert r["page_number"] is not None
        assert r["section_heading"] != ""
        assert r["chunk_type"] in ALLOWED_CHUNK_TYPES


def test_metadata_field_names_match_the_embedding_contract(records):
    """Sprint 2 story 2 reads these exact names off every record."""
    assert set(records[0]) == {
        "text",
        "source_file",
        "page_number",
        "element_type",
        "section_heading",
        "chunk_type",
    }


def test_no_record_has_empty_text(records):
    assert all(r["text"].strip() for r in records)


# =====================================================
# UNIT TESTS - clean.py functions, no corpus needed
# =====================================================

def test_normalise_text_expands_ligatures():
    assert clean.normalise_text("diﬀerent ﬁne ﬂow") == "different fine flow"


def test_normalise_text_collapses_whitespace():
    assert clean.normalise_text("too   many\n\nspaces") == "too many spaces"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("ISBN 978-1-98-852761-1", True),
        ("Published under a Creative Commons licence", True),
        ("Use edge protection wherever practicable.", False),
    ],
)
def test_is_boilerplate(text, expected):
    assert clean.is_boilerplate(text) is expected


@pytest.mark.parametrize(
    "element_type, heading, expected",
    [
        ("Table", "Glossary", "glossary"),
        ("NarrativeText", "Appendix A", "appendix"),
        ("NarrativeText", "Introduction", "prose"),
    ],
)
def test_classify_chunk_type(element_type, heading, expected):
    assert clean.classify_chunk_type(element_type, heading) == expected


def test_clean_elements_drops_unwanted_types_and_carries_headings():
    raw = [
        {"type": "Header", "text": "WorkSafe New Zealand", "metadata": {"page_number": 1}},
        {"type": "Title", "text": "Working at height", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "Use edge protection.", "metadata": {"page_number": 1}},
        {"type": "PageNumber", "text": "3", "metadata": {"page_number": 1}},
    ]

    records = clean.clean_elements(raw, SOURCE_FILE)["records"]

    assert all(r["element_type"] in clean.KEEP_TYPES for r in records)
    assert [r["text"] for r in records] == ["Working at height", "Use edge protection."]
    # the heading carries forward from the preceding Title
    assert all(r["section_heading"] == "Working at height" for r in records)
    assert all(r["source_file"] == SOURCE_FILE for r in records)


def test_clean_elements_removes_boilerplate():
    raw = [
        {"type": "Title", "text": "Introduction", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "ISBN 978-1-98-852761-1", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "Real guidance content.", "metadata": {"page_number": 1}},
    ]

    records = clean.clean_elements(raw, SOURCE_FILE)["records"]

    assert "978-1-98" not in "\n".join(r["text"] for r in records)
    assert any("Real guidance content." == r["text"] for r in records)
