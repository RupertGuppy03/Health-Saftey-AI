"""Helpers for checking citation data returned by the RAG pipeline."""

from collections.abc import Mapping
import json
import math
import os
from typing import Any

from dotenv import load_dotenv


DAG_CITATION_CRITERIA = (
    "Inspect citation_sources in actual_output and the retrieved chunk "
    "records in retrieval_context. Return True only if citation_sources "
    "contains at least one entry, every citation has a non-empty "
    "source_file and page_number, and every citation's source_file and "
    "page_number exactly match a retrieved chunk. Return False if a "
    "citation is missing, has incomplete metadata, or does not match. "
    "Do not infer citations from answer prose."
)


def has_citation_source(result: Mapping[str, Any]) -> bool:
    """Return whether a pipeline result contains a usable source citation."""

    sources = result.get("sources")
    if not isinstance(sources, list):
        return False

    return any(
        isinstance(source, Mapping)
        and isinstance(source.get("source_file"), str)
        and bool(source["source_file"].strip())
        for source in sources
    )


def score_citation_accuracy(
    question: str,
    answer: str,
    sources: list[Mapping[str, Any]],
    chunks: list[Mapping[str, Any]],
    *,
    model: str,
) -> tuple[float, str]:
    """Score citation presence and source/page alignment with DeepEval's DAGMetric."""

    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ.get("OPEN_AI_API_KEY", "")
    if not os.environ["OPENAI_API_KEY"]:
        raise RuntimeError("No OpenAI API key found for the DeepEval citation judge.")

    from deepeval.metrics import DAGMetric
    from deepeval.metrics.dag import (
        BinaryJudgementNode,
        DeepAcyclicGraph,
        VerdictNode,
    )
    from deepeval.test_case import LLMTestCase, SingleTurnParams

    citation_check = BinaryJudgementNode(
        criteria=DAG_CITATION_CRITERIA,
        children=[
            VerdictNode(verdict=True, score=10),
            VerdictNode(verdict=False, score=0),
        ],
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT,
        ],
    )

    metric = DAGMetric(
        name="Citation accuracy",
        dag=DeepAcyclicGraph(root_nodes=[citation_check]),
        threshold=1.0,
        model=model,
        include_reason=True,
        async_mode=False,
    )
    metric.measure(
        LLMTestCase(
            input=question,
            actual_output=json.dumps(
                {"answer": answer, "citation_sources": sources},
                ensure_ascii=False,
            ),
            retrieval_context=[
                json.dumps(
                    {
                        "text": chunk.get("text", ""),
                        "source_file": chunk.get("source_file"),
                        "page_number": chunk.get("page_number"),
                        "section_heading": chunk.get("section_heading"),
                    },
                    ensure_ascii=False,
                )
                for chunk in chunks
            ],
        )
    )

    score = metric.score
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
        or not 0 <= score <= 1
    ):
        raise RuntimeError(f"DeepEval DAGMetric returned an invalid citation score: {score!r}")

    return float(score), metric.reason or ""
