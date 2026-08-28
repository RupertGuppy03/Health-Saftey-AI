"""End-to-end style test that seeds an in-memory ChromaDB collection and runs
through the API without calling external services.
"""

from types import SimpleNamespace

import chromadb
from fastapi.testclient import TestClient

from src.api import app as api_app
from src.config import settings


class StubLLM:
    def __init__(self, response_text="Grounded by docs"):
        self.response_text = response_text

    def invoke(self, payload):
        return SimpleNamespace(content=self.response_text)


def test_end_to_end_seeded_collection(monkeypatch):
    # Create an ephemeral Chroma collection and seed it with one chunk.
    client = chromadb.EphemeralClient()
    name = "test_e2e_collection"
    collection = client.get_or_create_collection(name)

    dims = settings.EMBEDDING_DIMENSIONS
    vector = [0.0] * dims
    vector[0] = 1.0

    collection.upsert(
        ids=["doc1:p0001:0000"],
        documents=["Roof work requires edge protection and guardrails."],
        embeddings=[vector],
        metadatas=[
            {
                "source_file": "working-on-roofs.pdf",
                "page_number": 4,
                "section_heading": "Working at height",
            }
        ],
    )

    # Monkeypatch get_collection to return our seeded collection
    monkeypatch.setattr("src.vectorstore_client.get_collection", lambda name=None: collection)

    # Monkeypatch the embedder to return the vector we seeded so retrieval finds it
    monkeypatch.setattr("src.retrieval.retriever.embed_query", lambda q, client=None: vector)

    # Inject a stub LLM via the API dependency
    monkeypatch.setattr(api_app, "get_llm", lambda: StubLLM())

    test_client = TestClient(api_app.app)

    res = test_client.post("/ask", json={"question": "What edge protection do I need on a roof?"})
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["status"] == "ok"
    assert "edge protection" in body["answer"].lower() or "grounded" in body["answer"].lower()
    assert body["sources"] and body["sources"][0]["source_file"] == "working-on-roofs.pdf"
