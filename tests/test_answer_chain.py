"""Test the retrieval-to-LLM answer chain."""

from types import SimpleNamespace

from src.answer import answer_question


class StubLLM:
    """Tiny LLM stub that records the prompt and returns a synthetic answer."""

    def __init__(self, response_text="Grounded answer"):
        self.response_text = response_text
        self.calls = []

    def invoke(self, payload):
        self.calls.append(payload)
        return SimpleNamespace(content=self.response_text)


def _result(source_file, page_number, section_heading, text, chunk_id="chunk-1"):
    return {
        "chunk_id": chunk_id,
        "source_file": source_file,
        "page_number": page_number,
        "section_heading": section_heading,
        "text": text,
    }


def test_answer_question_returns_answer_and_sources():
    llm = StubLLM(response_text="Use edge protection on the roof.")

    result = answer_question(
        "What edge protection do I need on a roof?",
        retriever_fn=lambda question, n_results=None, collection_name=None: [
            _result(
                "working-on-roofs.pdf",
                4,
                "Working at height",
                "Roof work requires edge protection and guardrails.",
                chunk_id="roof-1",
            )
        ],
        llm=llm,
    )

    assert result["status"] == "ok"
    assert result["answer"] == "Use edge protection on the roof."
    assert result["sources"] == [
        {
            "source_file": "working-on-roofs.pdf",
            "page_number": 4,
            "section_heading": "Working at height",
            "chunk_id": "roof-1",
        }
    ]
    assert "Question: What edge protection do I need on a roof?" in llm.calls[0]["question"]
    assert "Roof work requires edge protection" in llm.calls[0]["context"]


def test_answer_question_reports_no_relevant_results():
    result = answer_question(
        "What is the capital of France?",
        retriever_fn=lambda question, n_results=None, collection_name=None: [],
        llm=StubLLM(),
    )

    assert result["status"] == "no_results"
    assert (
        "I can only assist with New Zealand workplace health and safety questions. "
        "Please ask a health and safety related question."
        == result["answer"]
    )
    assert result["sources"] == []


def test_answer_question_reports_openai_errors_without_crashing():
    class FailingLLM:
        def invoke(self, payload):
            raise RuntimeError("quota exceeded")

    result = answer_question(
        "What edge protection do I need on a roof?",
        retriever_fn=lambda question, n_results=None, collection_name=None: [
            _result(
                "working-on-roofs.pdf",
                4,
                "Working at height",
                "Roof work requires edge protection and guardrails.",
            )
        ],
        llm=FailingLLM(),
    )

    assert result["status"] == "error"
    assert "language model is currently unavailable" in result["answer"].lower()
    assert "quota exceeded" in result["error"]


def test_empty_question_is_rejected():
    try:
        answer_question(
            "   ",
            retriever_fn=lambda question, n_results=None, collection_name=None: [],
            llm=StubLLM(),
        )
    except ValueError as exc:
        assert "empty" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for blank question")


def test_off_topic_question_is_redirected_before_retrieval():
    def unexpected_retrieval(*args, **kwargs):
        raise AssertionError("Off-topic questions should not call retrieval")

    result = answer_question(
        "What is the capital of France?",
        retriever_fn=unexpected_retrieval,
        llm=StubLLM(),
    )

    assert result["status"] == "guardrail"
    assert "health and safety" in result["answer"].lower()


def test_external_safety_question_reports_missing_corpus_before_retrieval():
    def unexpected_retrieval(*args, **kwargs):
        raise AssertionError("External-jurisdiction questions should not call retrieval")

    result = answer_question(
        "Explain OSHA regulations for scaffolding.",
        retriever_fn=unexpected_retrieval,
        llm=StubLLM(),
    )

    assert result["status"] == "guardrail"
    assert "do not have information" in result["answer"].lower()


def test_legal_advice_question_is_refused_before_retrieval():
    def unexpected_retrieval(*args, **kwargs):
        raise AssertionError("Legal-advice questions should not call retrieval")

    result = answer_question(
        "Can you tell me if I have a strong employment law case?",
        retriever_fn=unexpected_retrieval,
        llm=StubLLM(),
    )

    assert result["status"] == "guardrail"
    assert "cannot provide legal advice" in result["answer"].lower()


def test_compensation_question_is_refused_before_retrieval():
    def unexpected_retrieval(*args, **kwargs):
        raise AssertionError("Compensation questions should not call retrieval")

    result = answer_question(
        "How much compensation should I claim after my injury?",
        retriever_fn=unexpected_retrieval,
        llm=StubLLM(),
    )

    assert result["status"] == "guardrail"
    assert "cannot provide legal advice" in result["answer"].lower()
