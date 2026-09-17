"""The Sprint 2 adversarial set, re-checked with conversation history enabled.

Story 10 lets earlier turns reach both the rewrite model and the answering prompt,
which is new ground: all 25 committed cases were signed off as a first question
with nothing before it. These run each case again with an ordinary health and
safety conversation already on screen.

Offline, so the claim made here is narrow and exact: **history changes nothing**.
The rewrite model is stubbed to behave as instructed (it leaves a question that is
unrelated to the conversation alone) and the answering model is a stub, so what is
proved is that the guardrail ordering still reaches the same decision, not that a
live model still words its refusal well. Twenty of the twenty-five cases are
decided by the guardrail before any model runs, and those are asserted outright.
The remaining five reach the language model, and their wording is the live run's
to judge — notebooks/S3_US10_followup_history.ipynb, committed for the DoD.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.answer import answer_question
from src.evaluation.edge_cases import evaluate_edge_case


FIXTURE = Path(__file__).with_name("edge_case_questions.json")

# What the user was asking about before the adversarial question arrived. In scope,
# ordinary, and the kind of exchange the guardrails have to keep holding underneath.
PRIOR_CONVERSATION = [
    {"role": "user", "content": "What edge protection do I need when working on a roof?"},
    {
        "role": "assistant",
        "content": (
            "Guardrails or another form of edge protection are required wherever a "
            "person could fall from a roof edge."
        ),
    },
]

CHUNK = {
    "chunk_id": "roofs:p0004:0000",
    "source_file": "working-on-roofs.pdf",
    "page_number": 4,
    "section_heading": "Working at height",
    "text": "Edge protection is required on any roof where a person could fall.",
}


def _cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class WellBehavedCondenser:
    """The rewrite model following its instructions: unrelated questions pass through."""

    def invoke(self, payload):
        return SimpleNamespace(content=payload["question"])


class RecordingLLM:
    """Stands in for the answering model, and reports whether it was reached."""

    def __init__(self):
        self.called = False

    def invoke(self, payload):
        self.called = True
        return SimpleNamespace(
            content="Edge protection is required wherever a person could fall."
        )


def _retriever(question, n_results=None, collection_name=None):
    return [dict(CHUNK)]


def _run(case, history, llm=None):
    return answer_question(
        case["question"],
        history=history,
        retriever_fn=_retriever,
        llm=llm or RecordingLLM(),
        condense_llm=WellBehavedCondenser(),
    )


def _guardrail_cases():
    """The cases the guardrail settles on its own, before any model is called."""

    return [case for case in _cases() if _run(case, None)["status"] == "guardrail"]


# =====================================================
# ACCEPTANCE TEST 3 — the guardrails behave as they did in Sprint 2
# =====================================================


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["id"])
def test_history_does_not_change_how_a_case_is_handled(case):
    """The central claim: a conversation in front of a question changes nothing."""

    with_history = _run(case, PRIOR_CONVERSATION)
    without_history = _run(case, None)

    assert with_history["status"] == without_history["status"]
    assert with_history["answer"] == without_history["answer"]
    assert with_history["sources"] == without_history["sources"]


@pytest.mark.parametrize("case", _guardrail_cases(), ids=lambda case: case["id"])
def test_a_guardrail_refusal_still_refuses_mid_conversation(case):
    result = _run(case, PRIOR_CONVERSATION)

    assert result["status"] == "guardrail"
    assert result["sources"] == []

    evaluation = evaluate_edge_case(case, result)
    assert evaluation["pass"], f"{case['id']}: {evaluation['notes']} — got: {result['answer']!r}"


@pytest.mark.parametrize("case", _guardrail_cases(), ids=lambda case: case["id"])
def test_a_refused_question_never_reaches_the_answering_model(case):
    """A refusal should cost nothing: no retrieval, no generation, no tokens."""

    llm = RecordingLLM()

    _run(case, PRIOR_CONVERSATION, llm=llm)

    assert not llm.called


def test_the_committed_fixture_is_still_the_full_sprint_2_set():
    """This suite is only evidence if it is re-running the signed-off questions."""

    assert len(_cases()) == 25


def test_most_of_the_set_is_settled_before_any_model_runs():
    """Guards the claim in this module's docstring against silent drift."""

    assert len(_guardrail_cases()) == 20
