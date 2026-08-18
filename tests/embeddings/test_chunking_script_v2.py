"""Tests for chunking, OpenAI embedding and ChromaDB ingestion.

No test here touches the real OpenAI API. Embedding calls go through a stub
client injected via the `client=` parameter, and ingestion uses an in-memory
Chroma collection, so the suite is free to run and never writes to
`vectorstore/`.
"""

import json
from types import SimpleNamespace

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
    """An in-memory Chroma collection standing in for the persisted one."""

    collection = chromadb.EphemeralClient().get_or_create_collection("test_ingest")
    monkeypatch.setattr(chunking, "get_collection", lambda name=None: collection)
    return collection


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


def test_ingest_namespaces_ids_by_source_document(chunk_file, memory_collection):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    stored = memory_collection.get()["ids"]

    assert all(i.startswith("doc-a.pdf::") for i in stored)


def test_namespacing_prevents_collisions_between_documents():
    # chunk_id restarts at CHUNK_00001 in every file, so without the source_file
    # prefix two documents would overwrite each other.
    a = {"source_file": "doc-a.pdf", "chunk_id": "CHUNK_00001"}
    b = {"source_file": "doc-b.pdf", "chunk_id": "CHUNK_00001"}

    assert chunking._chunk_record_id(a) != chunking._chunk_record_id(b)


def test_ingest_stores_the_expected_metadata(chunk_file, memory_collection, chunks):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    stored = memory_collection.get(include=["metadatas", "documents"])
    by_id = dict(zip(stored["ids"], stored["metadatas"]))

    for chunk in chunks:
        metadata = by_id[chunking._chunk_record_id(chunk)]

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

    target = chunking._chunk_record_id(chunks[0])

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
