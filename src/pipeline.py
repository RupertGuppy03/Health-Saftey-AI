"""One call from a question to a timed, structured answer.

The seam every caller goes through — the FastAPI route, the terminal script and
the evaluation runs — so the retrieval→LLM pipeline is invoked and timed in one
place rather than each caller wiring up its own stopwatch.

Nothing here answers the question itself. src.answer.answer_question does the
retrieval, the guardrails and the generation; this module only measures how long
that took and hands the result back in a fixed shape.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from src.answer import answer_question


def run_query(
    question: str,
    *,
    retriever_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    llm=None,
    collection_name: Optional[str] = None,
    n_results: Optional[int] = None,
) -> Dict[str, Any]:
    """Answer `question` and report how long the whole pipeline took.

    Returns answer, sources, latency_seconds, status and chunks. "chunks" is the
    full retrieved text, kept for the terminal script and the evals — the API
    response model drops it rather than sending several KB per request.

    Raises ValueError on an empty question so the caller decides how to report
    it: the API turns that into a readable 422, the terminal script lets it
    surface.
    """

    if not question or not question.strip():
        raise ValueError("Question cannot be empty")

    # perf_counter rather than time.time: it is monotonic, so a clock adjustment
    # mid-request cannot produce a negative or wildly wrong latency.
    started = time.perf_counter()

    result = answer_question(
        question,
        retriever_fn=retriever_fn,
        llm=llm,
        collection_name=collection_name,
        n_results=n_results,
    )

    latency_seconds = round(time.perf_counter() - started, 2)

    return {
        "answer": result.get("answer", ""),
        "sources": result.get("sources", []),
        "latency_seconds": latency_seconds,
        "status": result.get("status", "ok"),
        "chunks": result.get("chunks", []),
        # Only present when the pipeline failed. Logged by the API, never
        # returned to the browser.
        "error": result.get("error"),
    }
