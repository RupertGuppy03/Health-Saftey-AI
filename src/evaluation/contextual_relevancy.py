"""Score how relevant retrieved chunks are to a user's question."""

from typing import Optional, Protocol, TypedDict

from deepeval.metrics import ContextualRelevancyMetric
from deepeval.test_case import LLMTestCase


class ContextualRelevancyResult(TypedDict):
    score: float
    passed: bool
    reason: str


class _Metric(Protocol):
    score: Optional[float]
    reason: Optional[str]

    def measure(self, test_case: LLMTestCase) -> bool: ...


def score_contextual_relevancy(
    question: str,
    retrieval_context: list[str],
    *,
    threshold: float = 0.9,
    metric: Optional[_Metric] = None,
) -> ContextualRelevancyResult:
    """Score retrieved text against a question without generating an answer."""

    if not question or not question.strip():
        raise ValueError("Question cannot be empty")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("Threshold must be between 0 and 1")

    context = [chunk for chunk in retrieval_context if chunk and chunk.strip()]
    if not context:
        return {
            "score": 0.0,
            "passed": False,
            "reason": "No retrieved chunks were available to evaluate.",
        }

    if metric is None:
        metric = ContextualRelevancyMetric(threshold=threshold, model="gpt-4.1")

    metric.measure(LLMTestCase(input=question, retrieval_context=context))
    score = metric.score
    if score is None:
        raise RuntimeError("ContextualRelevancyMetric did not return a score")
    if not 0.0 <= score <= 1.0:
        raise RuntimeError(f"ContextualRelevancyMetric returned an invalid score: {score}")

    return {
        "score": float(score),
        "passed": score >= threshold,
        "reason": metric.reason or "",
    }
