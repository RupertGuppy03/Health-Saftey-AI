"""Tests for the timed pipeline wrapper (Sprint 3, story 1).

Nothing here touches OpenAI or Chroma: the retriever is a stub and the LLM is a
stub, so what is under test is the timing and the shape run_query returns.
"""

from types import SimpleNamespace

import pytest

from src import pipeline


CHUNK = {
    "chunk_id": "doc1:p0004:0000",
    "source_file": "working-on-roofs.pdf",
    "page_number": 4,
    "section_heading": "Working at height",
    "text": "Roof work requires edge protection and guardrails.",
}


class StubLLM:
    def invoke(self, payload):
        return SimpleNamespace(content="Edge protection is required.")


def stub_retriever(question, n_results=None, collection_name=None):
    return [dict(CHUNK)]


def test_run_query_reports_latency():
    result = pipeline.run_query(
        "What edge protection do I need for work at height?",
        retriever_fn=stub_retriever,
        llm=StubLLM(),
    )

    assert isinstance(result["latency_seconds"], float)
    assert result["latency_seconds"] >= 0


def test_run_query_returns_the_agreed_shape():
    result = pipeline.run_query(
        "What edge protection do I need for work at height?",
        retriever_fn=stub_retriever,
        llm=StubLLM(),
    )

    assert set(result) == {"answer", "sources", "latency_seconds", "status", "chunks", "error"}
    assert result["status"] == "ok"
    assert result["answer"]


def test_run_query_passes_sources_through_unchanged():
    result = pipeline.run_query(
        "What edge protection do I need for work at height?",
        retriever_fn=stub_retriever,
        llm=StubLLM(),
    )

    source = result["sources"][0]
    assert source["source_file"] == "working-on-roofs.pdf"
    assert source["page_number"] == 4
    assert source["section_heading"] == "Working at height"


@pytest.mark.parametrize("question", ["", "   "])
def test_run_query_rejects_an_empty_question(question):
    with pytest.raises(ValueError):
        pipeline.run_query(question, retriever_fn=stub_retriever, llm=StubLLM())


def test_run_query_answers_once(monkeypatch):
    """One question must not run the pipeline twice — retrieval costs an API call."""

    calls = []

    def counting_answer(question, **kwargs):
        calls.append(question)
        return {"answer": "a", "sources": [], "chunks": [], "status": "ok"}

    monkeypatch.setattr(pipeline, "answer_question", counting_answer)

    pipeline.run_query("What edge protection do I need for work at height?")

    assert len(calls) == 1
