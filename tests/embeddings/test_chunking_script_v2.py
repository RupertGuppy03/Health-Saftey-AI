"""Tests for chunking, OpenAI embedding and ChromaDB ingestion.

No test here touches the real OpenAI API. Embedding calls go through a stub
client injected via the `client=` parameter, and ingestion uses an in-memory
Chroma collection, so the suite is free to run and never writes to
`vectorstore/`.
"""

import json
from types import SimpleNamespace
from uuid import uuid4

import chromadb
import pytest

from src.embeddings import chunking_script_v2 as chunking


# =====================================================
# STUBS AND FIXTURES
# =====================================================

class StubEmbeddingsAPI:
    """Stands in for client.embeddings, recording what it was asked to embed."""

    def __init__(self, dimensions=chunking.EMBEDDING_DIMENSIONS):
        self.dimensions = dimensions
        self.calls = []

    def create(self, model, input):
        self.calls.append(list(input))

        data = [
            SimpleNamespace(
                index=position,
                # Encode the position in the vector so tests can prove ordering.
                embedding=[float(position + 1)] * self.dimensions,
            )
            for position in range(len(input))
        ]

        # Deliberately hand the items back out of order. The API does not
        # promise response order, and embed_texts must sort by .index.
        return SimpleNamespace(data=list(reversed(data)))


class StubOpenAIClient:
    def __init__(self, dimensions=chunking.EMBEDDING_DIMENSIONS):
        self.embeddings = StubEmbeddingsAPI(dimensions)

    @property
    def calls(self):
        return self.embeddings.calls


# Mirrors the shape of data/processed/*-CLEANED.json: a flat list of elements.
# Record 0 has no section_heading, like the front matter in five real documents.
CLEANED_ELEMENTS = [
    {
        "text": "This guideline provides practical guidance.",
        "source_file": "doc-a.pdf",
        "page_number": 1,
        "element_type": "NarrativeText",
        "section_heading": "",
        "chunk_type": "prose",
    },
    {
        "text": "Working at height",
        "source_file": "doc-a.pdf",
        "page_number": 2,
        "element_type": "Title",
        "section_heading": "Working at height",
        "chunk_type": "prose",
    },
    {
        "text": "Use edge protection wherever it is reasonably practicable.",
        "source_file": "doc-a.pdf",
        "page_number": 2,
        "element_type": "NarrativeText",
        "section_heading": "Working at height",
        "chunk_type": "prose",
    },
    {
        "text": "| Hazard | Control |\n| Fall | Guardrail |",
        "source_file": "doc-a.pdf",
        "page_number": 3,
        "element_type": "Table",
        "section_heading": "Hazard summary",
        "chunk_type": "table",
    },
]


@pytest.fixture
def cleaned_file(tmp_path):
    path = tmp_path / "doc-a-CLEANED.json"
    path.write_text(json.dumps(CLEANED_ELEMENTS), encoding="utf-8")
    return path


@pytest.fixture
def chunks(tmp_path, cleaned_file):
    return chunking.chunk_document(cleaned_file, tmp_path / "doc-a-CHUNKS.json")


@pytest.fixture
def memory_collection(monkeypatch):
    """An in-memory Chroma collection standing in for the persisted one.

    chromadb.EphemeralClient() returns a system shared across the process, so a
    fixed collection name would leak records between tests and make them
    order-dependent. Give each test its own collection instead.
    """

    client = chromadb.EphemeralClient()
    name = f"test_ingest_{uuid4().hex}"
    collection = client.get_or_create_collection(name)
    monkeypatch.setattr(chunking, "get_collection", lambda _name=None: collection)

    yield collection

    client.delete_collection(name)


# =====================================================
# CHUNKING
# =====================================================

def test_every_chunk_has_the_required_metadata(chunks):
    for chunk in chunks:
        for field in ("chunk_id", "text", "source_file", "page_number", "section_heading"):
            assert field in chunk, f"{field} missing from {chunk}"
            assert str(chunk[field]).strip(), f"{field} empty on {chunk['chunk_id']}"


def test_metadata_field_names_match_the_sprint_1_contract(chunks):
    # Story 2 DoD: the field names must match the chunking script exactly.
    assert set(chunks[0]) <= {
        "chunk_id",
        "text",
        "source_file",
        "page_number",
        "section_heading",
        "chunk_type",
    }


def test_chunk_type_preserved_for_a_homogeneous_section(chunks):
    table_chunks = [c for c in chunks if c["section_heading"] == "Hazard summary"]

    assert table_chunks
    assert all(c["chunk_type"] == "table" for c in table_chunks)


def test_empty_section_heading_is_backfilled(chunks):
    assert all(c["section_heading"].strip() for c in chunks)
    assert any(
        c["section_heading"] == chunking.FALLBACK_SECTION_HEADING for c in chunks
    )


def test_front_matter_is_not_merged_into_the_next_heading(chunks):
    """Regression test.

    Several real documents open with untitled front matter followed by an
    acknowledgements list, so taking "the next heading" would file the front
    matter under something like '> Beca Ltd' — a false citation.
    """

    front_matter = [c for c in chunks if "practical guidance" in c["text"]]

    assert len(front_matter) == 1
    assert front_matter[0]["section_heading"] == chunking.FALLBACK_SECTION_HEADING


def test_chunk_ids_are_unique_within_a_document(chunks):
    ids = [c["chunk_id"] for c in chunks]

    assert len(ids) == len(set(ids))


def test_output_file_matches_the_returned_chunks(tmp_path, cleaned_file):
    output = tmp_path / "out.json"
    returned = chunking.chunk_document(cleaned_file, output)

    assert json.loads(output.read_text(encoding="utf-8")) == returned


def test_a_long_section_is_split_with_overlap(tmp_path):
    sentences = " ".join(f"Sentence number {i} about site safety." for i in range(400))
    records = [
        {
            "text": sentences,
            "source_file": "long.pdf",
            "page_number": 1,
            "element_type": "NarrativeText",
            "section_heading": "Long section",
            "chunk_type": "prose",
        }
    ]
    source = tmp_path / "long-CLEANED.json"
    source.write_text(json.dumps(records), encoding="utf-8")

    produced = chunking.chunk_document(
        source, tmp_path / "long-CHUNKS.json", chunk_size=1000, chunk_overlap=200
    )

    assert len(produced) > 1
    assert all(len(c["text"]) <= 1000 for c in produced)


def test_page_number_is_the_first_page_of_the_section(chunks):
    heights = [c for c in chunks if c["section_heading"] == "Working at height"]

    assert heights
    assert all(c["page_number"] == 2 for c in heights)


# =====================================================
# VALIDATION
# =====================================================

def test_validate_chunks_accepts_good_chunks(chunks):
    chunking.validate_chunks(chunks)


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda c: c.pop("section_heading"), id="missing_field"),
        pytest.param(lambda c: c.update(section_heading=None), id="null_value"),
        pytest.param(lambda c: c.update(section_heading="   "), id="blank_value"),
        pytest.param(lambda c: c.pop("chunk_id"), id="missing_chunk_id"),
    ],
)
def test_validate_chunks_rejects_bad_metadata(chunks, mutation):
    mutation(chunks[0])

    with pytest.raises(ValueError):
        chunking.validate_chunks(chunks)


# =====================================================
# EMBEDDING
# =====================================================

def test_embed_texts_batches_instead_of_one_call_per_chunk():
    client = StubOpenAIClient()
    texts = [f"chunk {i}" for i in range(300)]

    chunking.embed_texts(texts, batch_size=128, client=client)

    assert len(client.calls) == 3, "expected 3 batched calls, not one per text"
    assert [len(c) for c in client.calls] == [128, 128, 44]


def test_embed_texts_returns_one_vector_per_text_at_full_width():
    client = StubOpenAIClient()
    texts = [f"chunk {i}" for i in range(10)]

    vectors = chunking.embed_texts(texts, client=client)

    assert len(vectors) == len(texts)
    assert all(len(v) == chunking.EMBEDDING_DIMENSIONS for v in vectors)


def test_embed_texts_preserves_input_order():
    # The stub returns each batch reversed, so this fails if embed_texts
    # trusts the response order instead of sorting by .index.
    client = StubOpenAIClient()

    vectors = chunking.embed_texts([f"chunk {i}" for i in range(300)], batch_size=128,
                                   client=client)

    assert vectors[0][0] == 1.0
    assert vectors[1][0] == 2.0
    assert vectors[128][0] == 1.0, "second batch should restart at position 1"


def test_embed_texts_makes_no_call_for_empty_input():
    client = StubOpenAIClient()

    assert chunking.embed_texts([], client=client) == []
    assert client.calls == []


def test_embed_texts_rejects_unexpected_dimensions():
    client = StubOpenAIClient(dimensions=384)

    with pytest.raises(ValueError, match="dimension"):
        chunking.embed_texts(["anything"], client=client)


def test_batches_are_split_again_when_they_exceed_the_token_cap():
    oversized = ["word " * 30_000] * 4

    batches = chunking._split_into_batches(oversized, batch_size=128)

    assert len(batches) > 1, "token cap should override the count-based batch size"


def test_batches_respect_the_count_limit():
    batches = chunking._split_into_batches([f"t{i}" for i in range(300)], batch_size=50)

    assert all(len(b) <= 50 for b in batches)
    assert sum(len(b) for b in batches) == 300


# =====================================================
# API KEY RESOLUTION
# =====================================================

@pytest.fixture
def no_dotenv(monkeypatch):
    """Stop load_dotenv repopulating the environment from the real .env."""

    monkeypatch.setattr(chunking, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("OPEN_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_project_key_name_is_accepted(no_dotenv, monkeypatch):
    monkeypatch.setenv("OPEN_AI_API_KEY", "sk-project-name")

    assert chunking._get_openai_client().api_key == "sk-project-name"


def test_sdk_key_name_is_accepted_as_a_fallback(no_dotenv, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-sdk-name")

    assert chunking._get_openai_client().api_key == "sk-sdk-name"


def test_project_key_name_wins_when_both_are_set(no_dotenv, monkeypatch):
    monkeypatch.setenv("OPEN_AI_API_KEY", "sk-project-name")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-sdk-name")

    assert chunking._get_openai_client().api_key == "sk-project-name"


def test_missing_key_raises_an_actionable_error(no_dotenv):
    with pytest.raises(RuntimeError, match="OPEN_AI_API_KEY"):
        chunking._get_openai_client()


# =====================================================
# CHROMADB INGESTION
# =====================================================

@pytest.fixture
def chunk_file(tmp_path, chunks):
    path = tmp_path / "ingest-CHUNKS.json"
    path.write_text(json.dumps(chunks), encoding="utf-8")
    return path


def test_ingest_stores_every_chunk(chunk_file, memory_collection, chunks):
    summary = chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    assert memory_collection.count() == len(chunks)
    assert summary["chunks_embedded"] == len(chunks)
    assert summary["count_before"] == 0
    assert summary["count_after"] == len(chunks)
    assert summary["embedding_model"] == chunking.EMBEDDING_MODEL


def test_ingest_uses_deterministic_ids(chunk_file, memory_collection, chunks):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    assert sorted(memory_collection.get()["ids"]) == sorted(chunking.build_chunk_ids(chunks))


def test_ids_are_stable_across_builds(chunks):
    assert chunking.build_chunk_ids(chunks) == chunking.build_chunk_ids(chunks)


def test_id_format_is_stem_page_index():
    record_id = chunking._chunk_record_id("PCBUs-Working-Together-GPG-7fcb7c71.pdf", 9, 42)

    assert record_id == "PCBUs-Working-Together-GPG-7fcb7c71:p0009:0042"


def test_ids_do_not_collide_between_documents():
    # chunk_id restarts at CHUNK_00001 in every file, so the ID must be built
    # from the document itself rather than from that counter.
    assert chunking._chunk_record_id("doc-a.pdf", 1, 0) != chunking._chunk_record_id("doc-b.pdf", 1, 0)


def test_ids_do_not_collide_within_a_page(chunks):
    ids = chunking.build_chunk_ids(chunks)

    assert len(ids) == len(set(ids))


def test_ids_ignore_the_chunk_id_counter(chunks):
    renumbered = [dict(c, chunk_id="CHUNK_99999") for c in chunks]

    assert chunking.build_chunk_ids(renumbered) == chunking.build_chunk_ids(chunks)


def test_ingest_stores_the_expected_metadata(chunk_file, memory_collection, chunks):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    stored = memory_collection.get(include=["metadatas", "documents"])
    by_id = dict(zip(stored["ids"], stored["metadatas"]))

    for chunk, record_id in zip(chunks, chunking.build_chunk_ids(chunks)):
        metadata = by_id[record_id]

        assert metadata["source_file"] == chunk["source_file"]
        assert metadata["page_number"] == chunk["page_number"]
        assert metadata["section_heading"] == chunk["section_heading"]


def test_no_stored_record_has_an_empty_metadata_field(chunk_file, memory_collection):
    # Story 2 DoD: no chunk is stored with a missing or empty metadata field.
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    for metadata in memory_collection.get(include=["metadatas"])["metadatas"]:
        for field in ("source_file", "page_number", "section_heading"):
            assert field in metadata
            assert str(metadata[field]).strip()


def test_ingesting_twice_does_not_duplicate_records(chunk_file, memory_collection, chunks):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())
    first = memory_collection.count()

    second_summary = chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    assert memory_collection.count() == first == len(chunks)
    assert second_summary["count_before"] == second_summary["count_after"]


def test_a_chunk_id_returns_exactly_one_record(chunk_file, memory_collection, chunks):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    target = chunking.build_chunk_ids(chunks)[0]

    assert len(memory_collection.get(ids=[target])["ids"]) == 1


def test_invalid_chunks_fail_before_any_embedding_is_paid_for(tmp_path, memory_collection):
    bad = [{"chunk_id": "CHUNK_00001", "text": "x", "source_file": "d.pdf",
            "page_number": 1, "section_heading": ""}]
    path = tmp_path / "bad-CHUNKS.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    client = StubOpenAIClient()

    with pytest.raises(ValueError):
        chunking.ingest_to_chromadb(path, client=client)

    assert client.calls == [], "validation must run before the API is called"


# =====================================================
# STALE PRUNING AND PROVENANCE (STORY 3)
# =====================================================

def _write_chunks(path, count, source_file="doc-a.pdf"):
    """A chunk file with `count` chunks, as chunk_document would emit."""

    records = [
        {
            "chunk_id": f"CHUNK_{i + 1:05}",
            "text": f"chunk text {i}",
            "source_file": source_file,
            "page_number": (i % 3) + 1,
            "section_heading": f"Section {i}",
            "chunk_type": "prose",
        }
        for i in range(count)
    ]
    path.write_text(json.dumps(records), encoding="utf-8")
    return records


def test_shrinking_a_document_removes_the_orphans(tmp_path, memory_collection):
    """Acceptance test 3: changed config re-embeds rather than leaving stale records.

    upsert only overwrites IDs that still exist, so without pruning the two
    dropped chunks would stay in the collection and keep being retrieved.
    """

    big = tmp_path / "big-CHUNKS.json"
    _write_chunks(big, 5)
    chunking.ingest_to_chromadb(big, client=StubOpenAIClient())
    before = set(memory_collection.get()["ids"])

    small = tmp_path / "small-CHUNKS.json"
    smaller_chunks = _write_chunks(small, 3)
    summary = chunking.ingest_to_chromadb(small, client=StubOpenAIClient())

    after = set(memory_collection.get()["ids"])

    assert memory_collection.count() == 3
    assert summary["stale_removed"] == 2
    assert after == set(chunking.build_chunk_ids(smaller_chunks))
    assert not (after - before), "no unexpected ids introduced"


def test_pruning_leaves_other_documents_alone(tmp_path, memory_collection):
    other = tmp_path / "other-CHUNKS.json"
    _write_chunks(other, 4, source_file="doc-b.pdf")
    chunking.ingest_to_chromadb(other, client=StubOpenAIClient())

    mine = tmp_path / "mine-CHUNKS.json"
    _write_chunks(mine, 2, source_file="doc-a.pdf")
    chunking.ingest_to_chromadb(mine, client=StubOpenAIClient())

    doc_b = memory_collection.get(where={"source_file": "doc-b.pdf"})["ids"]

    assert len(doc_b) == 4


def test_nothing_is_pruned_on_an_unchanged_rerun(tmp_path, memory_collection):
    path = tmp_path / "same-CHUNKS.json"
    _write_chunks(path, 4)
    chunking.ingest_to_chromadb(path, client=StubOpenAIClient())

    summary = chunking.ingest_to_chromadb(path, client=StubOpenAIClient())

    assert summary["stale_removed"] == 0
    assert summary["count_before"] == summary["count_after"] == 4


def test_records_carry_the_pipeline_provenance(chunk_file, memory_collection):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    metadata = memory_collection.get(include=["metadatas"])["metadatas"][0]

    assert metadata["pipeline_version"] == chunking.PIPELINE_VERSION
    assert metadata["embedding_model"] == chunking.EMBEDDING_MODEL
    assert metadata["chunk_size"] == chunking.CHUNK_SIZE
    assert metadata["chunk_overlap"] == chunking.CHUNK_OVERLAP


def test_provenance_reflects_the_config_actually_used(chunk_file, memory_collection):
    chunking.ingest_to_chromadb(
        chunk_file, chunk_size=1000, chunk_overlap=200, client=StubOpenAIClient()
    )

    metadata = memory_collection.get(include=["metadatas"])["metadatas"][0]

    assert metadata["chunk_size"] == 1000
    assert metadata["chunk_overlap"] == 200


def test_provenance_does_not_displace_the_locked_schema(chunk_file, memory_collection):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    for metadata in memory_collection.get(include=["metadatas"])["metadatas"]:
        for field in ("source_file", "page_number", "section_heading"):
            assert str(metadata[field]).strip()


def test_summary_reports_what_happened(chunk_file, memory_collection, chunks):
    summary = chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    assert summary["chunks_embedded"] == len(chunks)
    assert summary["stale_removed"] == 0
    assert summary["pipeline_version"] == chunking.PIPELINE_VERSION
