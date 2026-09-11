"""Where does a query's time actually go, and does the model choice change it?

Sprint 3 measured ~34s per question against a 5 second target. This splits a
query into retrieval and generation, then runs the same question and the same
retrieved context through several model settings so the comparison is fair.

Retrieval runs once and its context is reused, so every generation row is
answering from identical input and the only variable is the model setting.

    python3 scripts/measure_latency.py

Costs a handful of OpenAI calls: one embedding, and one generation per row.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from src.answer import _format_context, build_answer_chain
from src.config.settings import LLM_MODEL, LLM_TEMPERATURE, RETRIEVAL_TOP_K
from src.retrieval import retriever

QUESTION = "What edge protection do I need for work at height?"

# (label, model, extra ChatOpenAI kwargs). The first row is what the project
# runs today, so everything below is measured against it.
VARIANTS = [
    ("gpt-5-mini (as configured)", LLM_MODEL, {"temperature": LLM_TEMPERATURE}),
    ("gpt-5-mini reasoning=low", LLM_MODEL, {"reasoning_effort": "low"}),
    ("gpt-5-mini reasoning=minimal", LLM_MODEL, {"reasoning_effort": "minimal"}),
    ("gpt-4.1-mini (no reasoning)", "gpt-4.1-mini", {"temperature": LLM_TEMPERATURE}),
]


def _api_key():
    """The project's .env uses OPEN_AI_API_KEY; the SDK reads OPENAI_API_KEY."""

    load_dotenv(override=True)
    key = os.environ.get("OPEN_AI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("No OpenAI key found. Set OPEN_AI_API_KEY in .env.")
    return key


def main():
    print(f"Question: {QUESTION}\n")

    api_key = _api_key()

    started = time.perf_counter()
    results = retriever.retrieve(QUESTION, n_results=RETRIEVAL_TOP_K)
    retrieval_seconds = time.perf_counter() - started

    context = _format_context(results)
    print(f"RETRIEVAL  {retrieval_seconds:6.2f}s   "
          f"{len(results)} chunks, {len(context):,} characters of context\n")

    print(f"{'GENERATION':32} {'seconds':>9} {'answer chars':>13}")
    print("-" * 58)

    for label, model, kwargs in VARIANTS:
        try:
            llm = ChatOpenAI(model=model, api_key=api_key, **kwargs)
            chain = build_answer_chain(llm=llm)

            started = time.perf_counter()
            response = chain.invoke({"question": QUESTION, "context": context})
            seconds = time.perf_counter() - started

            answer = response.content if hasattr(response, "content") else str(response)
            print(f"{label:32} {seconds:8.2f}s {len(answer):13,}")
        except Exception as exc:
            print(f"{label:32} {'failed':>9}   {type(exc).__name__}: {exc}")

    print(f"\nRetrieval was {retrieval_seconds:.2f}s of the total in every row above.")


if __name__ == "__main__":
    main()
