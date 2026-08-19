"""Tests for the corpus overview helpers behind the notebook's status cell.

Nothing here touches the real vectorstore/ or data/processed/. Documents are
built under tmp_path and the collection is an in-memory Chroma one, so the
suite is free to run and cannot disturb the persisted store.
"""

import json
from uuid import uuid4

import chromadb
import pytest

from src.embeddings import corpus


# =====================================================
# FIXTURES
# =====================================================

def _cleaned_element(source_file, text="Some cleaned body text.", page_number=1):
    return {
        "text": text,
        "source_file": source_file,
        "page_number": page_number,
        "element_type": "NarrativeText",
        "section_heading": "Working at height",
        "chunk_type": "prose",
    }


def _write_document(root, slug, source_file, chunks=None):
    """A processed-document folder shaped like the real data/processed/<slug>/."""

    folder = root / slug
    folder.mkdir(parents=True)

    cleaned = folder / f"{slug}-CLEANED.json"
    cleaned.write_text(json.dumps([_cleaned_element(source_file)]), encoding="utf-8")

    if chunks is not None:
        records = [
            {
                "chunk_id": f"CHUNK_{i + 1:05}",
                "text": f"chunk text {i}",
                "source_file": source_file,
                "page_number": 1,
                "section_heading": "Working at height",
                "chunk_type": "prose",
            }
            for i in range(chunks)
        ]
        (folder / f"{slug}-CHUNKS.json").write_text(json.dumps(records), encoding="utf-8")

    return folder


@pytest.fixture
def processed_dir(tmp_path):
    """Two real documents, plus the two things that must be skipped."""

    root = tmp_path / "processed"
    root.mkdir()

    _write_document(root, "excavation_safety", "excavation-safety-gpg.pdf", chunks=3)
    _write_document(root, "working_on_roofs", "working-on-roofs-gpg.pdf")

    # A README file, as data/processed/ really has — not a directory.
    (root / "README.md").write_text("folder map", encoding="utf-8")

    # A directory with no cleaned output yet.
    (root / "not_processed_yet").mkdir()

    return root


@pytest.fixture
def memory_collection(monkeypatch):
    """In-memory collection standing in for the persisted one.

    EphemeralClient shares a system across the process, so each test gets its
    own collection name to stop records leaking between tests.
    """

    client = chromadb.EphemeralClient()
    name = f"test_corpus_{uuid4().hex}"
    collection = client.get_or_create_collection(name)
    monkeypatch.setattr(corpus, "get_collection", lambda _name=None: collection)

    yield collection

    client.delete_collection(name)


def _store(collection, source_file, count, page_number=1):
    """Put records in the collection, passing vectors explicitly.

    Chroma falls back to its own built-in embedder when embeddings are omitted,
    which would download a model. These tests only ever count metadata, so any
    consistent-width vector will do.
    """

    collection.add(
        ids=[f"{source_file}:{page_number}:{i}" for i in range(count)],
        documents=[f"text {i}" for i in range(count)],
        embeddings=[[float(i), 0.0, 0.0, 0.0] for i in range(count)],
        metadatas=[
            {
                "source_file": source_file,
                "page_number": page_number,
                "section_heading": "Working at height",
            }
            for _ in range(count)
        ],
    )


# =====================================================
# DOCUMENT DISCOVERY
# =====================================================

def test_lists_every_folder_holding_a_cleaned_file(processed_dir):
    names = [d["name"] for d in corpus.list_cleaned_documents(processed_dir)]

    assert names == ["excavation_safety", "working_on_roofs"]


def test_skips_folders_without_a_cleaned_file(processed_dir):
    names = [d["name"] for d in corpus.list_cleaned_documents(processed_dir)]

    assert "not_processed_yet" not in names


def test_skips_loose_files_such_as_the_readme(processed_dir):
    names = [d["name"] for d in corpus.list_cleaned_documents(processed_dir)]

    assert "README.md" not in names


def test_documents_are_sorted_by_name(tmp_path):
    root = tmp_path / "processed"
    root.mkdir()
    for slug in ("zebra_crossings", "asbestos_removal", "mobile_platforms"):
        _write_document(root, slug, f"{slug}.pdf")

    names = [d["name"] for d in corpus.list_cleaned_documents(root)]

    assert names == sorted(names)


def test_chunks_path_applies_the_cleaned_to_chunks_rename(processed_dir):
    document = corpus.list_cleaned_documents(processed_dir)[0]

    assert document["cleaned_json"].name == "excavation_safety-CLEANED.json"
    assert document["chunks_json"].name == "excavation_safety-CHUNKS.json"
    assert document["chunks_json"].parent == document["cleaned_json"].parent


def test_source_file_is_read_from_the_data_not_the_folder_name(processed_dir):
    # The vector store keys on the PDF filename, which is not the folder slug.
    document = corpus.list_cleaned_documents(processed_dir)[0]

    assert document["name"] == "excavation_safety"
    assert document["source_file"] == "excavation-safety-gpg.pdf"


def test_source_file_falls_back_to_empty_on_an_unreadable_cleaned_file(tmp_path):
    root = tmp_path / "processed"
    folder = root / "broken"
    folder.mkdir(parents=True)
    (folder / "broken-CLEANED.json").write_text("{not json", encoding="utf-8")

    document = corpus.list_cleaned_documents(root)[0]

    assert document["source_file"] == ""


# =====================================================
# INGESTION COUNTS
# =====================================================

def test_counts_records_per_source_file(memory_collection):
    _store(memory_collection, "excavation-safety-gpg.pdf", 3)
    _store(memory_collection, "working-on-roofs-gpg.pdf", 5, page_number=2)

    counts = corpus.ingested_chunk_counts()

    assert counts == {"excavation-safety-gpg.pdf": 3, "working-on-roofs-gpg.pdf": 5}


def test_counts_are_empty_for_an_empty_collection(memory_collection):
    assert corpus.ingested_chunk_counts() == {}


# =====================================================
# COMBINED STATUS
# =====================================================

def test_status_reports_zero_for_a_document_not_in_the_store(processed_dir, memory_collection):
    status = {e["name"]: e for e in corpus.corpus_status(processed_dir)}

    assert status["working_on_roofs"]["chunks_in_store"] == 0


def test_status_reports_the_stored_count_for_an_ingested_document(processed_dir, memory_collection):
    _store(memory_collection, "excavation-safety-gpg.pdf", 4)

    status = {e["name"]: e for e in corpus.corpus_status(processed_dir)}

    assert status["excavation_safety"]["chunks_in_store"] == 4


def test_status_reports_chunks_on_disk(processed_dir, memory_collection):
    status = {e["name"]: e for e in corpus.corpus_status(processed_dir)}

    # excavation_safety was written with 3 chunk records; working_on_roofs has none.
    assert status["excavation_safety"]["chunks_on_disk"] == 3
    assert status["working_on_roofs"]["chunks_on_disk"] == 0


def test_status_keeps_the_discovery_fields(processed_dir, memory_collection):
    entry = corpus.corpus_status(processed_dir)[0]

    for field in ("name", "cleaned_json", "chunks_json", "source_file"):
        assert field in entry


def test_status_covers_every_cleaned_document(processed_dir, memory_collection):
    status = corpus.corpus_status(processed_dir)

    assert len(status) == len(corpus.list_cleaned_documents(processed_dir))


# =====================================================
# TABLE RENDERING
# =====================================================

def test_table_lists_each_document_and_a_summary_line(processed_dir, memory_collection):
    _store(memory_collection, "excavation-safety-gpg.pdf", 4)

    table = corpus.format_status_table(corpus.corpus_status(processed_dir))

    assert "excavation_safety" in table
    assert "working_on_roofs" in table
    assert "1 of 2 documents in the collection" in table


def test_table_shows_a_dash_for_a_document_with_nothing_stored(processed_dir, memory_collection):
    table = corpus.format_status_table(corpus.corpus_status(processed_dir))

    roofs_line = next(l for l in table.splitlines() if "working_on_roofs" in l)

    assert "-" in roofs_line
