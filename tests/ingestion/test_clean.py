"""Spike tests for the deterministic cleaning step (src/ingestion/clean.py).

Runs on the cached Unstructured JSON — no API call. Asserts the US-07/US-09
style checks: boilerplate removed, a known table stays paired, and every record
carries the locked metadata fields.
"""

import json

import pytest

from src.ingestion import clean

ALLOWED_CHUNK_TYPES = {"prose", "table", "appendix", "glossary"}


@pytest.fixture(scope="module")
def records():
    json_path = clean._find_cached_json()
    elements = json.loads(json_path.read_text())
    return clean.clean_elements(elements, "PCBUs-Working-Together-GPG.pdf")["records"]


def test_boilerplate_removed(records):
    """No ISBN / copyright / disclaimer boilerplate survives cleaning."""
    blob = "\n".join(r["text"].lower() for r in records)
    assert "978-1-98" not in blob
    assert "creative commons" not in blob
    assert "this publication provides general guidance" not in blob


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


def test_ligatures_normalised(records):
    """Generic NFKC + glyph fixes remove the broken 'di(erent' style tokens."""
    blob = "\n".join(r["text"] for r in records)
    assert "di(erent" not in blob
    assert "ﬁ" not in blob and "ﬂ" not in blob


def test_every_record_has_locked_metadata(records):
    """US-09 schema: source_file, page_number, section_heading, chunk_type present."""
    assert records, "no records produced"
    for r in records:
        assert r["source_file"] == "PCBUs-Working-Together-GPG.pdf"
        assert r["page_number"] is not None
        assert r["section_heading"] != ""
        assert r["chunk_type"] in ALLOWED_CHUNK_TYPES
