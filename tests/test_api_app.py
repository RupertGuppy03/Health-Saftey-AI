"""Tests for the FastAPI backend (Sprint 3, story 1).

Nothing here calls OpenAI or Chroma. The LLM is injected through FastAPI's
dependency override so the real client is never constructed, and the retriever
is monkeypatched to return a fixed chunk.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api import app as api_app


CHUNK = {
    "chunk_id": "doc1:p0004:0000",
    "source_file": "working-on-roofs.pdf",
    "page_number": 4,
    "section_heading": "Working at height",
    "text": "Roof work requires edge protection and guardrails.",
}

QUESTION = "What edge protection do I need for work at height?"


class StubLLM:
    def __init__(self, response_text="Edge protection is required on roofs."):
        self.response_text = response_text

    def invoke(self, payload):
        return SimpleNamespace(content=self.response_text)


class FailingLLM:
    def invoke(self, payload):
        raise RuntimeError("quota exceeded")


def _client(monkeypatch, llm=None, retriever=None):
    """A TestClient with the LLM overridden and the retriever stubbed."""

    if retriever is None:
        def retriever(question, n_results=None, collection_name=None):
            return [dict(CHUNK)]

    monkeypatch.setattr("src.answer.retriever.retrieve", retriever)

    api_app.app.dependency_overrides[api_app.get_llm] = lambda: llm or StubLLM()

    client = TestClient(api_app.app)
    yield client

    api_app.app.dependency_overrides.clear()


@pytest.fixture
def client(monkeypatch):
    yield from _client(monkeypatch)


# =====================================================
# ACCEPTANCE TEST 1 — a question returns an answer and sources
# =====================================================


def test_chat_returns_an_answer_and_sources(client):
    response = client.post("/chat", json={"question": QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["answer"], str) and body["answer"]
    assert isinstance(body["sources"], list) and body["sources"]


# =====================================================
# ACCEPTANCE TEST 2 — every source carries document, page and section
# =====================================================


def test_each_source_has_document_page_and_section(client):
    body = client.post("/chat", json={"question": QUESTION}).json()

    for source in body["sources"]:
        assert source["source_file"] == "working-on-roofs.pdf"
        assert source["page_number"] == 4
        assert source["section_heading"] == "Working at height"


# =====================================================
# ACCEPTANCE TEST 3 — a missing or empty question is a readable 422
# =====================================================


def test_missing_question_is_a_readable_validation_error(client):
    response = client.post("/chat", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["message"] == "A question is required."


@pytest.mark.parametrize("question", ["", "   "])
def test_empty_question_is_a_readable_validation_error(client, question):
    response = client.post("/chat", json={"question": question})

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["message"] == "Question cannot be empty."


# =====================================================
# ACCEPTANCE TEST 4 — a pipeline failure is a status code, not a stack trace
# =====================================================


def test_llm_failure_returns_a_structured_error(monkeypatch):
    client = next(_client(monkeypatch, llm=FailingLLM()))

    response = client.post("/chat", json={"question": QUESTION})

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert body["message"]
    # The technical detail is logged on the backend, never sent to the browser.
    assert "quota exceeded" not in response.text
    assert "Traceback" not in response.text


def test_retrieval_failure_returns_a_structured_error(monkeypatch):
    def exploding_retriever(question, n_results=None, collection_name=None):
        raise RuntimeError("chroma is unreachable")

    client = next(_client(monkeypatch, retriever=exploding_retriever))

    response = client.post("/chat", json={"question": QUESTION})

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert "chroma is unreachable" not in response.text
    assert "Traceback" not in response.text


# =====================================================
# ACCEPTANCE TEST 5 — latency is reported on every successful call
# =====================================================


def test_successful_response_reports_latency(client):
    body = client.post("/chat", json={"question": QUESTION}).json()

    assert isinstance(body["latency_seconds"], float)
    assert body["latency_seconds"] >= 0


# =====================================================
# THE FIXED RESPONSE SHAPE
# =====================================================


def test_response_shape_is_fixed(client):
    body = client.post("/chat", json={"question": QUESTION}).json()

    # "chunks" carries several KB of retrieved text — it stays server-side.
    assert set(body) == {"answer", "sources", "latency_seconds", "status"}
    assert body["status"] == "ok"


def test_no_retrieved_chunks_reports_no_results(monkeypatch):
    client = next(_client(monkeypatch, retriever=lambda q, n_results=None, collection_name=None: []))

    response = client.post("/chat", json={"question": QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_results"
    assert body["sources"] == []


def test_ask_alias_returns_the_same_shape(client):
    chat = client.post("/chat", json={"question": QUESTION}).json()
    ask = client.post("/ask", json={"question": QUESTION}).json()

    assert set(chat) == set(ask)
    assert ask["status"] == "ok"
