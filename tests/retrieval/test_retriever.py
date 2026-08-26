"""Tests for query embedding and chunk retrieval.

No test here touches the real OpenAI API or the persisted store. The embedding
call goes through a stub client injected via `client=`, and the collection is an
in-memory Chroma one seeded with hand-written vectors, so "nearest neighbour" is
something the test controls rather than something it hopes for.
"""

from types import SimpleNamespace
from uuid import uuid4

import chromadb
import pytest

from src.config import settings
from src.retrieval import retriever


# =====================================================
# STUBS AND FIXTURES
# =====================================================

# Each seeded document occupies its own axis, so a query vector pointing down an
# axis is unambiguously nearest that document's chunks.
ROOFS_AXIS = 0
EXCAVATION_AXIS = 1


def _axis_vector(axis, dimensions=settings.EMBEDDING_DIMENSIONS):
    vector = [0.0] * dimensions
    vector[axis] = 1.0
    return vector


class StubEmbeddingsAPI:
    """Stands in for client.embeddings, recording how it was called."""

    def __init__(self, axis=ROOFS_AXIS, dimensions=settings.EMBEDDING_DIMENSIONS):
        self.axis = axis
        self.dimensions = dimensions
        self.calls = []

    def create(self, model, input):
        self.calls.append({"model": model, "input": list(input)})

        return SimpleNamespace(
            data=[SimpleNamespace(index=0, embedding=_axis_vector(self.axis, self.dimensions))]
        )


class StubOpenAIClient:
    def __init__(self, axis=ROOFS_AXIS, dimensions=settings.EMBEDDING_DIMENSIONS):
        self.embeddings = StubEmbeddingsAPI(axis, dimensions)

    @property
    def calls(self):
        return self.embeddings.calls


@pytest.fixture
def stub_client():
    """Answers every question with a vector pointing at the roofs document."""

    return StubOpenAIClient()


def _offset_vector(axis, index):
    vector = _axis_vector(axis)
    vector[2 + index] = 0.01 * (index + 1)
    return vector


def _seed(collection, source_file, axis, count, chunk_type="prose"):
    """Records shaped the way ingestion writes them, on one axis."""

    metadata = {
        "source_file": source_file,
        "page_number": 0,
        "page_start": 0,
        "page_end": 0,
        "section_heading": "Working at height",
        "pipeline_version": settings.PIPELINE_VERSION,
        "embedding_model": settings.EMBEDDING_MODEL,
    }

    for index in range(count):
        record = dict(metadata, page_number=index + 1, page_start=index + 1, page_end=index + 1)

        if chunk_type:
            record["chunk_type"] = chunk_type

        collection.upsert(
            ids=[f"{source_file}:p{index + 1:04d}:{index:04d}"],
            documents=[f"{source_file} guidance, chunk {index}"],
            # Tilt each successive chunk slightly off the axis so the distances
            # differ and ordering is a real assertion.
            embeddings=[_offset_vector(axis, index)],
            metadatas=[record],
        )


@pytest.fixture
def memory_collection(monkeypatch):
    """An in-memory collection standing in for the persisted one.

    EphemeralClient() returns a system shared across the process, so a fixed
    name would leak records between tests. Give each test its own.
    """

    client = chromadb.EphemeralClient()
    name = f"test_retrieve_{uuid4().hex}"
    collection = client.get_or_create_collection(name)
    monkeypatch.setattr(retriever, "get_collection", lambda _name=None: collection)

    yield collection

    client.delete_collection(name)


@pytest.fixture
def populated_collection(memory_collection):
    """Two documents, well clear of the default top-k so ranking matters."""

    _seed(memory_collection, "working-on-roofs.pdf", ROOFS_AXIS, 8)
    _seed(memory_collection, "excavation-safety.pdf", EXCAVATION_AXIS, 8)

    return memory_collection


# =====================================================
# EMBEDDING THE QUERY  (acceptance test 1)
# =====================================================

def test_query_is_embedded_with_the_configured_model(stub_client):
    retriever.embed_query("What edge protection do I need?", client=stub_client)

    assert stub_client.calls[0]["model"] == settings.EMBEDDING_MODEL


def test_query_model_matches_the_model_stored_on_the_records(
    populated_collection, stub_client
):
    """The real contract: query and stored vectors must come from one model."""

    retriever.retrieve("What edge protection do I need?", client=stub_client)

    stored = populated_collection.get(include=["metadatas"])["metadatas"]
    stored_models = {metadata["embedding_model"] for metadata in stored}

    assert stored_models == {stub_client.calls[0]["model"]}


def test_the_question_itself_is_what_gets_embedded(stub_client):
    retriever.embed_query("How deep can a trench be?", client=stub_client)

    assert stub_client.calls[0]["input"] == ["How deep can a trench be?"]


def test_a_wrong_width_vector_is_rejected():
    """A settings mistake should fail here, not as a Chroma dimension error."""

    narrow_client = StubOpenAIClient(dimensions=384)

    with pytest.raises(ValueError, match="dimension"):
        retriever.embed_query("What edge protection do I need?", client=narrow_client)


def test_an_empty_question_is_rejected(stub_client):
    with pytest.raises(ValueError, match="empty question"):
        retriever.embed_query("   ", client=stub_client)


class RecordingCollection:
    """Passes everything through to a real collection, noting the query kwargs."""

    def __init__(self, collection):
        self._collection = collection
        self.query_kwargs = {}

    def count(self):
        return self._collection.count()

    def query(self, **kwargs):
        self.query_kwargs = kwargs
        return self._collection.query(**kwargs)


def test_retrieval_never_uses_chroma_built_in_embedder(
    populated_collection, stub_client, monkeypatch
):
    """query_texts= would use Chroma's 384-dim model against 1536-dim vectors."""

    recording = RecordingCollection(populated_collection)
    monkeypatch.setattr(retriever, "get_collection", lambda _name=None: recording)

    retriever.retrieve("What edge protection do I need?", client=stub_client)

    assert "query_embeddings" in recording.query_kwargs
    assert "query_texts" not in recording.query_kwargs


# =====================================================
# HOW MANY CHUNKS COME BACK  (acceptance test 2)
# =====================================================

def test_configured_top_k_is_within_the_agreed_band():
    assert 4 <= settings.RETRIEVAL_TOP_K <= 6


def test_retrieval_returns_the_configured_number_of_chunks(
    populated_collection, stub_client
):
    results = retriever.retrieve("What edge protection do I need?", client=stub_client)

    assert len(results) == settings.RETRIEVAL_TOP_K
    assert 4 <= len(results) <= 6


def test_the_count_can_be_overridden_for_one_call(populated_collection, stub_client):
    results = retriever.retrieve(
        "What edge protection do I need?", n_results=4, client=stub_client
    )

    assert len(results) == 4


def test_asking_for_more_than_the_collection_holds_returns_what_exists(
    memory_collection, stub_client
):
    _seed(memory_collection, "working-on-roofs.pdf", ROOFS_AXIS, 2)

    results = retriever.retrieve(
        "What edge protection do I need?", n_results=6, client=stub_client
    )

    assert len(results) == 2


def test_an_empty_collection_returns_nothing_without_calling_the_api(
    memory_collection, stub_client
):
    results = retriever.retrieve("What edge protection do I need?", client=stub_client)

    assert results == []
    assert stub_client.calls == []


# =====================================================
# WHAT EACH RESULT CARRIES  (acceptance test 3)
# =====================================================

def test_every_result_carries_the_locked_metadata(populated_collection, stub_client):
    results = retriever.retrieve("What edge protection do I need?", client=stub_client)

    for result in results:
        assert result["source_file"]
        assert result["page_number"]
        assert result["section_heading"]


def test_every_result_carries_its_chunk_id_and_text(populated_collection, stub_client):
    results = retriever.retrieve("What edge protection do I need?", client=stub_client)

    for result in results:
        assert result["chunk_id"]
        assert result["text"]


def test_a_record_without_chunk_type_yields_none(memory_collection, stub_client):
    _seed(memory_collection, "working-on-roofs.pdf", ROOFS_AXIS, 6, chunk_type=None)

    results = retriever.retrieve("What edge protection do I need?", client=stub_client)

    assert all(result["chunk_type"] is None for result in results)


# =====================================================
# RANKING  (acceptance test 4)
# =====================================================

def test_a_question_about_one_document_retrieves_that_document(
    populated_collection, stub_client
):
    results = retriever.retrieve("What edge protection do I need?", client=stub_client)

    assert any(result["source_file"] == "working-on-roofs.pdf" for result in results)


def test_the_nearest_document_dominates_the_results(populated_collection, stub_client):
    """A roofs question should not come back led by the excavation document."""

    results = retriever.retrieve("What edge protection do I need?", client=stub_client)

    assert results[0]["source_file"] == "working-on-roofs.pdf"


def test_a_different_question_retrieves_a_different_document(populated_collection):
    excavation_client = StubOpenAIClient(axis=EXCAVATION_AXIS)

    results = retriever.retrieve("How deep can a trench be?", client=excavation_client)

    assert results[0]["source_file"] == "excavation-safety.pdf"


def test_results_are_ordered_nearest_first(populated_collection, stub_client):
    results = retriever.retrieve("What edge protection do I need?", client=stub_client)

    distances = [result["distance"] for result in results]

    assert distances == sorted(distances)


def test_ranks_are_numbered_from_one(populated_collection, stub_client):
    results = retriever.retrieve("What edge protection do I need?", client=stub_client)

    assert [result["rank"] for result in results] == list(range(1, len(results) + 1))


# =====================================================
# OUTPUT
# =====================================================

def test_format_results_shows_source_page_and_heading(populated_collection, stub_client):
    results = retriever.retrieve("What edge protection do I need?", client=stub_client)

    rendered = retriever.format_results(results)

    assert "working-on-roofs.pdf" in rendered
    assert "page 1" in rendered
    assert "Working at height" in rendered


def test_format_results_handles_no_results():
    assert "No chunks retrieved" in retriever.format_results([])


def test_format_results_truncates_long_chunk_text():
    result = {
        "rank": 1,
        "chunk_id": "doc:p0001:0000",
        "text": "word " * 200,
        "source_file": "doc.pdf",
        "page_number": 1,
        "section_heading": "Working at height",
        "chunk_type": "prose",
        "distance": 0.1,
    }

    rendered = retriever.format_results([result], text_chars=50)

    assert "..." in rendered
    assert len(rendered) < 400
