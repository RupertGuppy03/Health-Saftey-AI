"""Integration tests for the API wrapper around the retrieval→LLM chain.

These tests do not call the real OpenAI API — they override the LLM
dependency with a stub and monkeypatch the retriever to return deterministic
results.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api import app as api_app


class StubLLM:
    def __init__(self, response_text="Stubbed answer"):
        self.response_text = response_text
        self.calls = []

    def invoke(self, payload):
        self.calls.append(payload)
        return SimpleNamespace(content=self.response_text)


@pytest.fixture
def client(monkeypatch):
    # Override the get_llm dependency to return a stub LLM
    monkeypatch.setattr(api_app, "get_llm", lambda: StubLLM(response_text="Grounded by docs"))

    # Override the retriever used by the answer module so we don't touch Chroma
    def fake_retriever(question, n_results=None, collection_name=None):
        return [
            {
                "chunk_id": "doc1:p0001:0000",
                "source_file": "working-on-roofs.pdf",
                "page_number": 4,
                "section_heading": "Working at height",
                "text": "Roof work requires edge protection and guardrails.",
            }
        ]

    monkeypatch.setattr("src.answer.retriever.retrieve", fake_retriever)

    return TestClient(api_app.app)


def test_api_ask_returns_ok(client):
    res = client.post("/ask", json={"question": "What edge protection do I need on a roof?"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "edge protection" in body["answer"].lower() or "grounded" in body["answer"].lower()
    assert body["sources"][0]["source_file"] == "working-on-roofs.pdf"


def test_api_ask_no_results(monkeypatch):
    # Client with retriever returning nothing
    monkeypatch.setattr("src.answer.retriever.retrieve", lambda q, n_results=None, collection_name=None: [])
    monkeypatch.setattr(api_app, "get_llm", lambda: StubLLM())
    client = TestClient(api_app.app)

    res = client.post("/ask", json={"question": "What is the capital of France?"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "no_results"
    assert body["sources"] == []


def test_api_ask_handles_llm_error(monkeypatch):
    class FailingLLM:
        def invoke(self, payload):
            raise RuntimeError("quota exceeded")

    monkeypatch.setattr(api_app, "get_llm", lambda: FailingLLM())
    monkeypatch.setattr("src.answer.retriever.retrieve", lambda q, n_results=None, collection_name=None: [
        {
            "chunk_id": "doc1:p0001:0000",
            "source_file": "working-on-roofs.pdf",
            "page_number": 4,
            "section_heading": "Working at height",
            "text": "Roof work requires edge protection and guardrails.",
        }
    ])

    client = TestClient(api_app.app)
    res = client.post("/ask", json={"question": "What edge protection do I need on a roof?"})
    assert res.status_code == 500
    body = res.json()
    assert body["detail"]["status"] == "error"
    assert "quota exceeded" in body["detail"]["error"]
