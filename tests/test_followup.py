"""Tests for follow-up questions with conversation context (Sprint 3, story 10).

Nothing here calls OpenAI or Chroma: the retriever is a stub, the answering model
is a stub, and the rewrite model is a stub that records what it was asked. What is
under test is the order the guardrails run in, what reaches each model, and that a
question asked with no history behaves exactly as it did before this story.
"""

from types import SimpleNamespace

import pytest

from src import answer as answer_module
from src.answer import answer_question, condense_question
from src.config import settings


ROOF_CHUNK = {
    "chunk_id": "roofs:p0004:0000",
    "source_file": "working-on-roofs.pdf",
    "page_number": 4,
    "section_heading": "Working at height",
    "text": "Edge protection is required on any roof where a person could fall.",
}

SCAFFOLD_CHUNK = {
    "chunk_id": "scaffold:p0009:0000",
    "source_file": "scaffolding-gpg.pdf",
    "page_number": 9,
    "section_heading": "Scaffold inspection",
    "text": "A scaffold must be inspected before first use.",
}

CONVERSATION = [
    {"role": "user", "content": "What edge protection do I need on a roof?"},
    {"role": "assistant", "content": "Guardrails are required where a person could fall."},
]


class StubLLM:
    """The answering model. Records the payload it was handed."""

    def __init__(self, response_text="Edge protection is required."):
        self.response_text = response_text
        self.payloads = []

    def invoke(self, payload):
        self.payloads.append(payload)
        return SimpleNamespace(content=self.response_text)


class StubCondenser:
    """The rewrite model. Returns a fixed rewrite and records what it was asked."""

    def __init__(self, rewritten="What edge protection is needed on a smaller roof?"):
        self.rewritten = rewritten
        self.payloads = []

    def invoke(self, payload):
        self.payloads.append(payload)
        return SimpleNamespace(content=self.rewritten)


class NeverCalled:
    """Fails the test if the rewrite model is reached at all."""

    def invoke(self, payload):
        raise AssertionError("The rewrite model should not have been called.")


def _retriever(chunks):
    """A retriever that records the question it was asked to search on."""

    asked = []

    def retrieve(question, n_results=None, collection_name=None):
        asked.append(question)
        return [dict(chunk) for chunk in chunks]

    retrieve.asked = asked
    return retrieve


# =====================================================
# ACCEPTANCE TEST 1 — a follow-up stays on the earlier topic
# =====================================================


def test_a_follow_up_without_the_topic_is_answered_rather_than_refused():
    """Without the rewrite this is refused outright: no health and safety keyword."""

    retriever = _retriever([ROOF_CHUNK])

    result = answer_question(
        "What about on a smaller one?",
        history=CONVERSATION,
        retriever_fn=retriever,
        llm=StubLLM(),
        condense_llm=StubCondenser(),
    )

    assert result["status"] == "ok"
    assert result["sources"]


def test_the_rewritten_question_is_what_retrieval_searches_on():
    retriever = _retriever([ROOF_CHUNK])

    answer_question(
        "What about on a smaller one?",
        history=CONVERSATION,
        retriever_fn=retriever,
        llm=StubLLM(),
        condense_llm=StubCondenser(),
    )

    assert retriever.asked == ["What edge protection is needed on a smaller roof?"]


def test_the_rewrite_model_is_shown_the_conversation():
    condenser = StubCondenser()

    answer_question(
        "What about on a smaller one?",
        history=CONVERSATION,
        retriever_fn=_retriever([ROOF_CHUNK]),
        llm=StubLLM(),
        condense_llm=condenser,
    )

    transcript = condenser.payloads[0]["transcript"]
    assert "What edge protection do I need on a roof?" in transcript
    assert condenser.payloads[0]["question"] == "What about on a smaller one?"


def test_the_answering_model_is_given_the_earlier_turns():
    llm = StubLLM()

    answer_question(
        "What about on a smaller one?",
        history=CONVERSATION,
        retriever_fn=_retriever([ROOF_CHUNK]),
        llm=llm,
        condense_llm=StubCondenser(),
    )

    assert llm.payloads[0]["history"] == [
        ("user", "What edge protection do I need on a roof?"),
        ("assistant", "Guardrails are required where a person could fall."),
    ]


# =====================================================
# ACCEPTANCE TEST 4 — the sources belong to the follow-up
# =====================================================


def test_the_sources_are_the_follow_ups_and_not_the_earlier_questions():
    """Retrieval runs on the rewritten follow-up, so the citations follow it."""

    retriever = _retriever([SCAFFOLD_CHUNK])

    result = answer_question(
        "And what about those?",
        history=CONVERSATION,
        retriever_fn=retriever,
        llm=StubLLM(),
        condense_llm=StubCondenser("How often must a scaffold be inspected?"),
    )

    assert [source["source_file"] for source in result["sources"]] == ["scaffolding-gpg.pdf"]


# =====================================================
# ACCEPTANCE TEST 3 — the guardrails behave as they did in Sprint 2
# =====================================================


def test_an_off_topic_question_is_still_refused_mid_conversation():
    """The rewrite is told to leave an unrelated question alone, so the check still fires."""

    result = answer_question(
        "What is the capital of France?",
        history=CONVERSATION,
        retriever_fn=_retriever([ROOF_CHUNK]),
        llm=StubLLM(),
        condense_llm=StubCondenser("What is the capital of France?"),
    )

    assert result["status"] == "guardrail"
    assert "only assist with New Zealand workplace health and safety" in result["answer"]
    assert result["sources"] == []


def test_legal_advice_is_refused_on_the_users_own_words_before_any_rewrite():
    """A rewrite cannot soften a legal question if it never sees it."""

    result = answer_question(
        "Should I sue my employer?",
        history=CONVERSATION,
        retriever_fn=_retriever([ROOF_CHUNK]),
        llm=StubLLM(),
        condense_llm=NeverCalled(),
    )

    assert result["status"] == "guardrail"
    assert "cannot provide legal advice" in result["answer"]


def test_an_external_standard_is_refused_on_the_users_own_words():
    result = answer_question(
        "What does ISO 45001 require?",
        history=CONVERSATION,
        retriever_fn=_retriever([ROOF_CHUNK]),
        llm=StubLLM(),
        condense_llm=NeverCalled(),
    )

    assert result["status"] == "guardrail"
    assert "do not have information on that topic" in result["answer"]


def test_a_rewrite_that_invents_safety_wording_still_answers_nothing():
    """The second line of defence, for when the keyword check is fooled.

    A misbehaving rewrite can bolt "workplace safety" onto anything and get past a
    keyword allowlist — that is the S3-02 weakness, and this story does not fix it.
    What holds instead is that the corpus has nothing to say about jokes, so the
    question is refused for want of grounding rather than answered from training data.
    """

    llm = StubLLM()

    result = answer_question(
        "Tell me a joke.",
        history=CONVERSATION,
        retriever_fn=_retriever([]),
        llm=llm,
        condense_llm=StubCondenser("Tell me a joke about workplace safety."),
    )

    assert result["status"] == "no_results"
    assert result["sources"] == []
    assert llm.payloads == [], "nothing should have been generated without context"


# =====================================================
# NO HISTORY MEANS NO CHANGE
# =====================================================


def test_a_standalone_question_never_calls_the_rewrite_model():
    """The common case costs nothing extra: no history, no second model call."""

    result = answer_question(
        "What edge protection do I need on a roof?",
        retriever_fn=_retriever([ROOF_CHUNK]),
        llm=StubLLM(),
        condense_llm=NeverCalled(),
    )

    assert result["status"] == "ok"


def test_a_pronoun_question_with_no_history_is_still_refused():
    """Nothing about this story makes a bare "what about those?" answerable."""

    result = answer_question(
        "What about on a smaller one?",
        retriever_fn=_retriever([ROOF_CHUNK]),
        llm=StubLLM(),
        condense_llm=NeverCalled(),
    )

    assert result["status"] == "guardrail"


def test_no_history_sends_no_history_to_the_answering_model():
    llm = StubLLM()

    answer_question(
        "What edge protection do I need on a roof?",
        retriever_fn=_retriever([ROOF_CHUNK]),
        llm=llm,
    )

    assert llm.payloads[0]["history"] == []


# =====================================================
# THE REWRITE ITSELF
# =====================================================


def test_condense_returns_the_question_untouched_when_there_is_no_history():
    assert condense_question("What PPE do I need?", history=None) == "What PPE do I need?"
    assert condense_question("What PPE do I need?", history=[]) == "What PPE do I need?"


def test_a_failed_rewrite_falls_back_to_the_original_question():
    """A question answered as if standalone beats a question that errors."""

    class Failing:
        def invoke(self, payload):
            raise RuntimeError("quota exceeded")

    assert condense_question("What about those?", history=CONVERSATION, llm=Failing()) == "What about those?"


@pytest.mark.parametrize("reply", ["", "   "])
def test_an_empty_rewrite_falls_back_to_the_original_question(reply):
    assert condense_question("What about those?", history=CONVERSATION, llm=StubCondenser(reply)) == "What about those?"


def test_a_rambling_rewrite_falls_back_to_the_original_question():
    """A model that explained itself instead of rewriting is not a question."""

    rambling = "Certainly! " + ("The user appears to be asking about roofs. " * 30)

    assert condense_question("What about those?", history=CONVERSATION, llm=StubCondenser(rambling)) == "What about those?"


# =====================================================
# THE MODELS ARE CONFIGURED, NOT HARDCODED
# =====================================================


def _built(monkeypatch):
    """Record the arguments _build_chat_llm is called with, without building one."""

    calls = []

    def fake_build(model, temperature, reasoning_effort=None, api_key=None):
        calls.append(
            {"model": model, "temperature": temperature, "reasoning_effort": reasoning_effort}
        )
        return StubLLM()

    monkeypatch.setattr(answer_module, "_build_chat_llm", fake_build)
    answer_module._get_openai_chat_llm.cache_clear()
    answer_module._get_condense_llm.cache_clear()

    return calls


@pytest.fixture(autouse=True)
def _clear_model_caches():
    """The clients are cached for the process; a test must not inherit another's."""

    yield
    answer_module._get_openai_chat_llm.cache_clear()
    answer_module._get_condense_llm.cache_clear()


def test_the_answering_model_comes_from_settings(monkeypatch):
    calls = _built(monkeypatch)

    answer_module._get_openai_chat_llm()

    assert calls == [
        {
            "model": settings.LLM_MODEL,
            "temperature": settings.LLM_TEMPERATURE,
            "reasoning_effort": settings.LLM_REASONING_EFFORT,
        }
    ]


def test_the_rewrite_model_comes_from_its_own_settings(monkeypatch):
    calls = _built(monkeypatch)

    answer_module._get_condense_llm()

    assert calls == [
        {
            "model": settings.HISTORY_CONDENSE_MODEL,
            "temperature": settings.HISTORY_CONDENSE_TEMPERATURE,
            "reasoning_effort": settings.HISTORY_CONDENSE_REASONING_EFFORT,
        }
    ]


def test_changing_the_answering_model_in_settings_needs_no_code_change(monkeypatch):
    monkeypatch.setattr(answer_module, "LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setattr(answer_module, "LLM_REASONING_EFFORT", "minimal")
    calls = _built(monkeypatch)

    answer_module._get_openai_chat_llm()

    assert calls[0]["model"] == "gpt-4.1-mini"
    assert calls[0]["reasoning_effort"] == "minimal"


def test_no_reasoning_effort_is_sent_when_none_is_configured():
    """None means "send nothing", not "send the string none"."""

    built = answer_module._build_chat_llm(
        model="gpt-5-mini", temperature=0.1, reasoning_effort=None, api_key="test-key"
    )

    assert built.reasoning_effort is None


def test_a_configured_reasoning_effort_reaches_the_client():
    built = answer_module._build_chat_llm(
        model="gpt-5-mini", temperature=0.1, reasoning_effort="minimal", api_key="test-key"
    )

    assert built.reasoning_effort == "minimal"
