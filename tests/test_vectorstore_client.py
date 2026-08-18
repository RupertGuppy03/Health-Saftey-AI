"""Tests for the persisted ChromaDB client (Sprint 2, story 1).

Every test redirects CHROMA_PERSIST_DIR at a tmp_path, so the real
`vectorstore/` folder is never touched. Nothing here needs the OpenAI API:
vectors are supplied directly, which is also how the real ingestion path works.
"""

import chromadb
import pytest
from chromadb.api.client import SharedSystemClient

from src import vectorstore_client
from src.config.settings import CHROMA_COLLECTION_NAME


DIMENSIONS = 1536


def _vector(seed):
    return [float(seed)] * DIMENSIONS


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Point the client at a throwaway directory instead of ./vectorstore."""

    persist_dir = tmp_path / "vectorstore"
    # The module reads this global at call time, so patching it here is enough.
    monkeypatch.setattr(vectorstore_client, "CHROMA_PERSIST_DIR", persist_dir)

    # Chroma caches a client per path; clear it so each test really starts cold.
    SharedSystemClient.clear_system_cache()
    yield persist_dir
    SharedSystemClient.clear_system_cache()


def test_persist_directory_is_created_on_demand(isolated_store):
    assert not isolated_store.exists()

    vectorstore_client.get_client()

    assert isolated_store.is_dir()


def test_data_is_written_under_the_persist_directory(isolated_store):
    collection = vectorstore_client.get_collection()
    collection.add(ids=["a"], documents=["hello"], embeddings=[_vector(1)])

    assert any(isolated_store.iterdir()), "expected Chroma files on disk"


def test_a_named_collection_is_used_rather_than_the_default(isolated_store):
    collection = vectorstore_client.get_collection()

    assert collection.name == CHROMA_COLLECTION_NAME
    assert collection.name != "default"


def test_collection_name_can_be_overridden_for_debugging(isolated_store):
    collection = vectorstore_client.get_collection("hs_construction_scratch")

    assert collection.name == "hs_construction_scratch"


def test_get_collection_is_idempotent(isolated_store):
    first = vectorstore_client.get_collection()
    second = vectorstore_client.get_collection()

    assert first.name == second.name


def test_count_is_zero_for_a_fresh_collection(isolated_store):
    count = vectorstore_client.count_collection()

    assert isinstance(count, int)
    assert count == 0


def test_count_reflects_stored_items(isolated_store):
    collection = vectorstore_client.get_collection()
    collection.add(
        ids=["a", "b", "c"],
        documents=["one", "two", "three"],
        embeddings=[_vector(1), _vector(2), _vector(3)],
    )

    assert vectorstore_client.count_collection() == 3


def test_the_collection_survives_a_restart(isolated_store):
    """Story 1: after a restart the collection loads without re-embedding."""

    collection = vectorstore_client.get_collection()
    collection.add(
        ids=["a", "b"],
        documents=["one", "two"],
        embeddings=[_vector(1), _vector(2)],
        metadatas=[{"source_file": "d.pdf"}, {"source_file": "d.pdf"}],
    )

    # Drop every cached client so the next call genuinely reopens from disk.
    SharedSystemClient.clear_system_cache()

    assert vectorstore_client.count_collection() == 2

    reopened = vectorstore_client.get_collection()
    stored = reopened.get(ids=["a"], include=["documents", "metadatas"])

    assert stored["documents"] == ["one"]
    assert stored["metadatas"][0]["source_file"] == "d.pdf"


def test_metadata_round_trips_unchanged(isolated_store):
    collection = vectorstore_client.get_collection()
    metadata = {
        "source_file": "working-on-roofs.pdf",
        "page_number": 12,
        "section_heading": "Edge protection",
        "chunk_type": "prose",
    }
    collection.add(ids=["a"], documents=["text"], embeddings=[_vector(1)],
                   metadatas=[metadata])

    assert collection.get(ids=["a"], include=["metadatas"])["metadatas"][0] == metadata


def test_upsert_overwrites_rather_than_appends(isolated_store):
    collection = vectorstore_client.get_collection()
    collection.upsert(ids=["a"], documents=["first"], embeddings=[_vector(1)])
    collection.upsert(ids=["a"], documents=["second"], embeddings=[_vector(2)])

    assert collection.count() == 1
    assert collection.get(ids=["a"], include=["documents"])["documents"] == ["second"]


def test_a_wrong_width_query_vector_is_rejected(isolated_store):
    """Pins the contract that makes query_texts unusable on this collection.

    The collection holds 1536-dimension OpenAI vectors, but Chroma keeps its own
    384-dimension embedder attached. Calling query(query_texts=...) would embed
    the question with that built-in model and fail exactly like this, so callers
    must embed the query themselves and pass query_embeddings.
    """

    collection = vectorstore_client.get_collection()
    collection.add(ids=["a"], documents=["hello"], embeddings=[_vector(1)])

    with pytest.raises(Exception, match="1536"):
        collection.query(query_embeddings=[[0.1] * 384], n_results=1)


def test_query_with_a_matching_width_vector_works(isolated_store):
    collection = vectorstore_client.get_collection()
    collection.add(
        ids=["a", "b"],
        documents=["one", "two"],
        embeddings=[_vector(1), _vector(9)],
        metadatas=[{"source_file": "d.pdf"}, {"source_file": "d.pdf"}],
    )

    results = collection.query(query_embeddings=[_vector(1)], n_results=2)

    assert results["ids"][0][0] == "a", "nearest vector should come back first"
    assert results["metadatas"][0][0]["source_file"] == "d.pdf"
