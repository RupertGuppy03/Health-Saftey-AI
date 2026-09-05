"""Generate grounded answers from retrieved Chroma chunks using LangChain."""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI

from src.config.prompts import GROUNDING_SYSTEM_PROMPT
from src.config.settings import (
    LLM_MODEL,
    LLM_TEMPERATURE,
    RETRIEVAL_RELEVANCE_THRESHOLD,
    RETRIEVAL_TOP_K,
)
from src.retrieval import retriever


def _get_openai_chat_llm(model: Optional[str] = None, api_key: Optional[str] = None):
    """Return the configured chat model, or a caller-supplied stub for tests.

    Try the most commonly used constructor signature first (model_name/openai_api_key),
    then fall back to older signatures (model/api_key) so the code works across
    langchain-openai versions.
    """

    if model is None:
        model = LLM_MODEL

    if api_key is None:
        load_dotenv(override=True)
        api_key = os.environ.get("OPEN_AI_API_KEY") or os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "No OpenAI API key found. Set OPEN_AI_API_KEY "
            "(or OPENAI_API_KEY) in your .env file."
        )

    # Try modern signature first
    try:
        return ChatOpenAI(model_name=model, temperature=LLM_TEMPERATURE, openai_api_key=api_key)
    except TypeError:
        # Fallback to older kwarg names
        try:
            return ChatOpenAI(model=model, temperature=LLM_TEMPERATURE, api_key=api_key)
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Failed to construct ChatOpenAI: {exc}")


def _format_context(results: Iterable[Dict[str, Any]]) -> str:
    """Inline retrieved chunks with citations so the model can answer with provenance."""

    chunks: List[str] = []

    for result in results:
        source_file = result.get("source_file") or "unknown source"
        section_heading = result.get("section_heading") or "(no section heading)"
        page_number = result.get("page_number")
        text = (result.get("text") or "").strip()

        page_text = f" page {page_number}" if page_number is not None else ""
        chunks.append(
            f"[Source: {source_file}{page_text} | Section: {section_heading}]\n{text}"
        )

    return "\n\n".join(chunks)


def _source_metadata(results: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the fragment of each retrieved record needed for attribution."""

    return [
        {
            "source_file": result.get("source_file"),
            "page_number": result.get("page_number"),
            "section_heading": result.get("section_heading"),
            "chunk_id": result.get("chunk_id"),
        }
        for result in results
    ]


def _no_context_answer(question: str) -> str:
    """Choose the guardrail response when retrieval returns no usable context."""

    lower_question = question.casefold()
    health_safety_signal = re.search(
        r"\b(workplace|work|employer|employee|hazard|safety|health|injur|"
        r"scaffold|chemical|heights?|whs|osha|iso|worksafe)\b",
        lower_question,
    )
    if health_safety_signal:
        return (
            "I do not have information on that topic within my available health and "
            "safety knowledge base."
        )
    return (
        "I can only assist with New Zealand workplace health and safety questions. "
        "Please ask a health and safety related question."
    )


def _preflight_guardrail_answer(question: str) -> Optional[str]:
    """Handle unambiguous scope cases before retrieval can introduce noise."""

    lower_question = question.casefold()
    legal_advice_signal = re.search(
        r"\b(sue|legal|law|lawyer|solicitor|court|compensation|claim|"
        r"dispute|employment law|strong case|win a case)\b",
        lower_question,
    )
    if legal_advice_signal:
        return (
            "I cannot provide legal advice. You may wish to seek advice from a "
            "qualified legal professional."
        )

    external_scope_signal = re.search(
        r"\b(australian?|australia|osha|singapore|iso\s*(?:45001|31000)?)\b",
        lower_question,
    )
    if external_scope_signal:
        return (
            "I do not have information on that topic within my available health and "
            "safety knowledge base."
        )

    health_safety_signal = re.search(
        r"\b(workplace|work|employer|employee|hazard|safety|health|injur|"
        r"scaffold|chemical|heights?|whs|worksafe|unsafe|accident|ppe)\b",
        lower_question,
    )
    if not health_safety_signal:
        return (
            "I can only assist with New Zealand workplace health and safety questions. "
            "Please ask a health and safety related question."
        )
    return None


def build_answer_chain(llm=None):
    """Create a LangChain prompt-to-LLM chain for grounded answers."""

    if llm is None:
        llm = _get_openai_chat_llm()

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", GROUNDING_SYSTEM_PROMPT),
            (
                "human",
                "Question: {question}\n\nRetrieved context:\n{context}\n\nAnswer using only the supplied context, and cite the source document and section heading for each relevant point.",
            ),
        ]
    )

    if isinstance(llm, Runnable):
        return prompt | llm

    if hasattr(llm, "invoke"):

        def _invoke_with_prompt(payload):
            if isinstance(payload, dict):
                question = payload.get("question", "")
                if not str(question).startswith("Question:"):
                    payload = {
                        "question": f"Question: {question}",
                        "context": payload.get("context", ""),
                    }
                return llm.invoke(payload)
            return llm.invoke(payload)

        return RunnableLambda(_invoke_with_prompt)

    raise TypeError(f"Unsupported LLM type: {type(llm).__name__}")


def answer_question(
    question: str,
    *,
    retriever_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    llm=None,
    collection_name: Optional[str] = None,
    n_results: Optional[int] = None,
):
    """Retrieve relevant chunks, ask the LLM for a grounded answer, and return metadata.

    The returned dict carries the retrieved records under "chunks" so a caller
    can show what the answer was actually built from without retrieving again.
    """

    if not question or not question.strip():
        raise ValueError("Question cannot be empty")

    preflight_answer = _preflight_guardrail_answer(question)
    if preflight_answer is not None:
        return {
            "answer": preflight_answer,
            "sources": [],
            "chunks": [],
            "status": "guardrail",
        }

    if retriever_fn is None:
        retriever_fn = retriever.retrieve

    if n_results is None:
        n_results = RETRIEVAL_TOP_K

    try:
        results = retriever_fn(question, n_results=n_results, collection_name=collection_name)
    except Exception as exc:  # pragma: no cover - surfaces through structured error payload
        return {
            "answer": "I could not retrieve the relevant information because the retrieval step failed.",
            "sources": [],
            "chunks": [],
            "status": "error",
            "error": f"Retrieval failed: {exc}",
        }

    if results:
        filtered_results = []
        for result in results:
            similarity_score = result.get("similarity_score")
            if similarity_score is None:
                filtered_results.append(result)
                continue
            if float(similarity_score) >= RETRIEVAL_RELEVANCE_THRESHOLD:
                filtered_results.append(result)
        results = filtered_results

    if not results:
        return {
            "answer": _no_context_answer(question),
            "sources": [],
            "chunks": [],
            "status": "no_results",
        }

    try:
        chain = build_answer_chain(llm=llm)
        response = chain.invoke({"question": question, "context": _format_context(results)})
        answer = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        return {
            "answer": "I could not generate an answer because the language model is currently unavailable.",
            "sources": [],
            "chunks": results,
            "status": "error",
            "error": f"OpenAI API error: {exc}",
        }

    return {
        "answer": answer.strip(),
        "sources": _source_metadata(results),
        "chunks": results,
        "status": "ok",
    }
