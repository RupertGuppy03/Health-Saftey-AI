"""Offline tests for Contextual Relevancy scoring."""

import pytest

from src.evaluation.contextual_relevancy import score_contextual_relevancy


class StubMetric:
    def __init__(self, score=0.95, reason="Relevant retrieval context."):
        self.score = score
        self.reason = reason
        self.test_case = None

    def measure(self, test_case):
        self.test_case = test_case
        return self.score >= 0.9


def test_score_contextual_relevancy_measures_the_question_and_retrieved_chunks():
    metric = StubMetric()

    result = score_contextual_relevancy(
        "What controls prevent falls?",
        ["Use edge protection.", "A separate chunk about office lighting."],
        metric=metric,
    )

    assert metric.test_case.input == "What controls prevent falls?"
    assert metric.test_case.retrieval_context == [
        "Use edge protection.",
        "A separate chunk about office lighting.",
    ]
    assert result == {
        "score": 0.95,
        "passed": True,
        "reason": "Relevant retrieval context.",
    }


def test_score_contextual_relevancy_fails_below_the_threshold():
    result = score_contextual_relevancy(
        "What controls prevent falls?",
        ["An unrelated chunk."],
        threshold=0.9,
        metric=StubMetric(score=0.4),
    )

    assert result["score"] == 0.4
    assert result["passed"] is False


def test_score_contextual_relevancy_returns_zero_when_no_chunks_are_retrieved():
    metric = StubMetric()

    result = score_contextual_relevancy("What controls prevent falls?", [], metric=metric)

    assert result == {
        "score": 0.0,
        "passed": False,
        "reason": "No retrieved chunks were available to evaluate.",
    }
    assert metric.test_case is None


@pytest.mark.parametrize("question", ["", "   "])
def test_score_contextual_relevancy_rejects_an_empty_question(question):
    with pytest.raises(ValueError, match="Question cannot be empty"):
        score_contextual_relevancy(question, ["A retrieved chunk."], metric=StubMetric())


def test_score_contextual_relevancy_rejects_an_invalid_threshold():
    with pytest.raises(ValueError, match="Threshold must be between 0 and 1"):
        score_contextual_relevancy(
            "What controls prevent falls?",
            ["A retrieved chunk."],
            threshold=1.1,
            metric=StubMetric(),
        )
