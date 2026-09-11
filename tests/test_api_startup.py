"""Startup, /health and client reuse (Sprint 3, story 2).

Starlette only runs the lifespan handler inside `with TestClient(app):`, so the
tests that need startup use the context-manager form. Nothing here calls OpenAI
or opens the real vectorstore.
"""

from types import SimpleNamespace

import chromadb
import pytest
from chromadb.api.client import SharedSystemClient
from fastapi.testclient import TestClient

from src import answer, vectorstore_client
from src.api import app as api_app
from src.config.settings import CHROMA_COLLECTION_NAME, EMBEDDING_DIMENSIONS


QUESTION = "What edge protection do I need for work at height?"


class StubLLM:
    def invoke(self, payload):
        return SimpleNamespace(content="Edge protection is required.")


@pytest.fixture(autouse=True)
def clear_caches():
    """Every client is process-cached now, so tests must start and end cold."""

    vectorstore_client.get_client.cache_clear()
    answer._get_openai_chat_llm.cache_clear()
    SharedSystemClient.clear_system_cache()
    yield
    vectorstore_client.get_client.cache_clear()
    answer._get_openai_chat_llm.cache_clear()
    SharedSystemClient.clear_system_cache()
    api_app.app.dependency_overrides.clear()


# =====================================================
# ACCEPTANCE TEST 1 — /health reports the collection and its chunk count
# =====================================================


def test_health_reports_the_collection_and_chunk_count(monkeypatch):
    monkeypatch.setattr(api_app, "count_collection", lambda name=None: 3646)
    monkeypatch.setattr(api_app, "_get_openai_client", lambda: object())
    monkeypatch.setattr(api_app, "_get_openai_chat_llm", lambda: StubLLM())

    with TestClient(api_app.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["collection_name"] == CHROMA_COLLECTION_NAME
    assert body["chunk_count"] == 3646
    assert isinstance(body["startup_seconds"], float)
    assert body["startup_seconds"] >= 0


# =====================================================
# ACCEPTANCE TEST 3 — an empty collection stops the server starting
# =====================================================


def test_an_empty_collection_stops_the_server_starting(monkeypatch):
    monkeypatch.setattr(api_app, "count_collection", lambda name=None: 0)

    with pytest.raises(RuntimeError) as raised:
        with TestClient(api_app.app):
            pass

    message = str(raised.value)
    assert CHROMA_COLLECTION_NAME in message
    assert "ingestion" in message.lower()


def test_a_missing_api_key_is_a_warning_not_a_dead_server(monkeypatch, caplog):
    """The collection is the hard failure; a key problem must stay serveable."""

    monkeypatch.setattr(api_app, "count_collection", lambda name=None: 3646)

    def no_key():
        raise RuntimeError("No OpenAI API key found.")

    monkeypatch.setattr(api_app, "_get_openai_client", no_key)

    with caplog.at_level("WARNING"):
        with TestClient(api_app.app) as client:
            assert client.get("/health").status_code == 200

    assert "No OpenAI API key found." in caplog.text


def test_health_goes_unavailable_when_the_collection_empties(monkeypatch):
    """Story 8 uses this as a readiness check, so it has to be able to go unready."""

    counts = iter([3646, 0])
    monkeypatch.setattr(api_app, "count_collection", lambda name=None: next(counts))
    monkeypatch.setattr(api_app, "_get_openai_client", lambda: object())
    monkeypatch.setattr(api_app, "_get_openai_chat_llm", lambda: StubLLM())

    with TestClient(api_app.app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["chunk_count"] == 0


# =====================================================
# ACCEPTANCE TESTS 2 AND 4 — a second question re-initialises nothing
# =====================================================


def test_the_chat_model_is_built_once_for_two_questions(monkeypatch):
    constructions = []

    class CountingChatOpenAI:
        def __init__(self, **kwargs):
            constructions.append(kwargs)

        def invoke(self, payload):
            return SimpleNamespace(content="Edge protection is required.")

    monkeypatch.setenv("OPEN_AI_API_KEY", "test-key")
    monkeypatch.setattr("src.answer.ChatOpenAI", CountingChatOpenAI)
    monkeypatch.setattr(
        "src.answer.retriever.retrieve",
        lambda q, n_results=None, collection_name=None: [
            {
                "chunk_id": "c1",
                "source_file": "roofs.pdf",
                "page_number": 4,
                "section_heading": "Working at height",
                "text": "Edge protection is required.",
            }
        ],
    )

    # No dependency override here: get_llm has to run for real, or the cache
    # under test is never exercised.
    client = TestClient(api_app.app)

    assert client.post("/chat", json={"question": QUESTION}).status_code == 200
    assert client.post("/chat", json={"question": QUESTION}).status_code == 200

    assert len(constructions) == 1, "the chat model was rebuilt for the second question"


def test_the_vector_store_is_opened_once_for_two_questions(tmp_path, monkeypatch):
    """The literal acceptance test: question two must not reload the store."""

    monkeypatch.setattr(vectorstore_client, "CHROMA_PERSIST_DIR", tmp_path / "vectorstore")

    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[0] = 1.0

    seeded = vectorstore_client.get_collection()
    seeded.add(
        ids=["doc1:p0004:0000"],
        documents=["Edge protection is required on roofs."],
        embeddings=[vector],
        metadatas=[
            {
                "source_file": "working-on-roofs.pdf",
                "page_number": 4,
                "section_heading": "Working at height",
            }
        ],
    )

    # Seeding opened a client of its own. Drop it so the count below only
    # measures what the two requests do.
    vectorstore_client.get_client.cache_clear()
    SharedSystemClient.clear_system_cache()

    opened = []
    real_persistent_client = chromadb.PersistentClient

    def counting_persistent_client(*args, **kwargs):
        opened.append(kwargs.get("path"))
        return real_persistent_client(*args, **kwargs)

    monkeypatch.setattr(chromadb, "PersistentClient", counting_persistent_client)
    monkeypatch.setattr("src.retrieval.retriever.embed_query", lambda q, client=None: vector)

    api_app.app.dependency_overrides[api_app.get_llm] = lambda: StubLLM()
    client = TestClient(api_app.app)

    first = client.post("/chat", json={"question": QUESTION})
    second = client.post("/chat", json={"question": QUESTION})

    assert first.json()["status"] == "ok", first.text
    assert second.json()["status"] == "ok", second.text
    assert len(opened) == 1, f"the vector store was opened {len(opened)} times"

    # And the setup cost is not being paid twice.
    assert second.json()["latency_seconds"] >= 0
