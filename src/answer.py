"""Generate grounded answers from retrieved Chroma chunks using LangChain."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any, Callable, Dict, Iterable, List, Optional

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI

from src import conversation
from src.config.prompts import CONDENSE_QUESTION_PROMPT, GROUNDING_SYSTEM_PROMPT
from src.config.settings import (
    HISTORY_CONDENSE_MODEL,
    HISTORY_CONDENSE_REASONING_EFFORT,
    HISTORY_CONDENSE_TEMPERATURE,
    LLM_MODEL,
    LLM_REASONING_EFFORT,
    LLM_TEMPERATURE,
    RETRIEVAL_RELEVANCE_THRESHOLD,
    RETRIEVAL_TOP_K,
)
from src.retrieval import retriever


def _resolve_api_key(api_key: Optional[str] = None) -> str:
    """The OpenAI key under whichever of the two names the .env uses."""

    if api_key is None:
        load_dotenv(override=True)
        api_key = os.environ.get("OPEN_AI_API_KEY") or os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "No OpenAI API key found. Set OPEN_AI_API_KEY "
            "(or OPENAI_API_KEY) in your .env file."
        )

    return api_key


def _build_chat_llm(
    model: str,
    temperature: float,
    reasoning_effort: Optional[str] = None,
    api_key: Optional[str] = None,
):
    """Construct a ChatOpenAI from settings — the only place that does.

    Try the most commonly used constructor signature first (model_name/openai_api_key),
    then fall back to older signatures (model/api_key) so the code works across
    langchain-openai versions.

    reasoning_effort is only passed when one is configured. Sending nothing is not
    the same as sending a value the caller happens to think is the default, and the
    answering model's signed-off behaviour is the behaviour it has with the
    parameter absent.
    """

    api_key = _resolve_api_key(api_key)

    options = {"temperature": temperature}

    if reasoning_effort is not None:
        options["reasoning_effort"] = reasoning_effort

    # Try modern signature first
    try:
        return ChatOpenAI(model_name=model, openai_api_key=api_key, **options)
    except TypeError:
        # Fallback to older kwarg names
        try:
            return ChatOpenAI(model=model, api_key=api_key, **options)
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Failed to construct ChatOpenAI: {exc}")


@lru_cache(maxsize=1)
def _get_openai_chat_llm(model: Optional[str] = None, api_key: Optional[str] = None):
    """Return the configured chat model, or a caller-supplied stub for tests.

    Cached: constructing the client per request made every question pay for
    setup that belongs to the first one (story 2). The API warms it at startup.
    """

    return _build_chat_llm(
        model=model if model is not None else LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        reasoning_effort=LLM_REASONING_EFFORT,
        api_key=api_key,
    )


@lru_cache(maxsize=1)
def _get_condense_llm(model: Optional[str] = None, api_key: Optional[str] = None):
    """The model that rewrites a follow-up into a standalone question.

    Separate from the answering model so the rewrite can be retuned, or moved to a
    cheaper model, without touching the answer path. Cached and warmed at startup
    for the same reason the answering client is.
    """

    return _build_chat_llm(
        model=model if model is not None else HISTORY_CONDENSE_MODEL,
        temperature=HISTORY_CONDENSE_TEMPERATURE,
        reasoning_effort=HISTORY_CONDENSE_REASONING_EFFORT,
        api_key=api_key,
    )


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


def _strip_inline_citations(answer: str) -> str:
    """Keep model-written source blocks out of the answer shown by the UI."""

    return re.split(r"(?im)^\s*Sources?:\s*$", answer, maxsplit=1)[0].strip()


def _answer_has_no_support(answer: str) -> bool:
    """Detect a grounded response that says the retrieved context is insufficient."""

    return bool(
        re.search(
            r"\b("
            r"not enough information|"
            r"does not (?:include|contain|provide)|"
            r"do not have information|"
            r"cannot answer|"
            r"(?:cannot|can['’]t) answer|"
            r"outside (?:the )?(?:scope|available)"
            r")\b",
            answer,
            flags=re.IGNORECASE,
        )
    )


# Words that mark a question as workplace health and safety, used by both
# guardrails below so the two cannot drift apart.
#
# Matched with a trailing \w* wherever a plural or derivative is likely. The
# original list was exact singulars inside \b(...)\b, so "hazards", "chemicals",
# "scaffolding", "accidents" and "employees" all failed to register as in scope,
# and "injur" matched no real English word at all. The construction vocabulary
# (roof, ladder, harness, trench, excavation) was missing entirely, which is why
# "What edge protection do I need on a roof?" — the corpus's primary use case —
# was being refused as off topic.
#
# This is a keyword allowlist, which is a blunt instrument: anything phrased
# without one of these words still reads as out of scope. Sprint 4's out-of-scope
# handling story is where that gets a better mechanism.
HEALTH_SAFETY_SIGNAL = re.compile(
    r"\b("
    r"workplace|work\w*|employer\w*|employee\w*|hazard\w*|safety|health\w*|"
    r"injur\w*|scaffold\w*|chemical\w*|heights?|whs|worksafe|unsafe|"
    r"accident\w*|ppe|"
    # Construction and site vocabulary — the corpus is building and construction.
    r"roof\w*|ladder\w*|excavat\w*|trench\w*|asbestos|harness\w*|guardrail\w*|"
    r"edge protection|fall|falls|falling|fallen|construction|demolition|"
    r"machinery|plant|forklift\w*|crane\w*|silica|dust|noise|electric\w*|"
    r"respirator\w*|protective|equipment|first aid|incident\w*|risk\w*|"
    r"confined space\w*|lifting|manual handling|helmet\w*|toxic|fume\w*|vibration"
    r")\b"
)

# Questions about another country's rules or an external standard. Safety
# related, but outside this New Zealand knowledge base.
EXTERNAL_SCOPE_SIGNAL = re.compile(
    r"\b(australian?|australia|osha|singapore|iso\s*(?:45001|31000)?)\b"
)


def _no_context_answer(question: str) -> str:
    """Choose the guardrail response when retrieval returns no usable context."""

    lower_question = question.casefold()
    # An external-standard question is safety related, so it gets the
    # "not in my knowledge base" answer rather than the off-topic redirect.
    health_safety_signal = HEALTH_SAFETY_SIGNAL.search(
        lower_question
    ) or EXTERNAL_SCOPE_SIGNAL.search(lower_question)
    if health_safety_signal:
        return (
            "I do not have information on that topic within my available health and "
            "safety knowledge base."
        )
    return (
        "I can only assist with New Zealand workplace health and safety questions. "
        "Please ask a health and safety related question."
    )


def _intent_refusal(question: str) -> Optional[str]:
    """Refusals decided by what the question asks for: legal advice, or a standard
    this knowledge base does not hold.

    Split out from the scope check below because these fire on a signal being
    present, which a two-word follow-up can carry just as well as a full question.
    They are therefore judged on what the user actually typed, before any rewrite
    gets the chance to put different words in their mouth.
    """

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

    if EXTERNAL_SCOPE_SIGNAL.search(lower_question):
        return (
            "I do not have information on that topic within my available health and "
            "safety knowledge base."
        )

    return None


def _scope_refusal(question: str) -> Optional[str]:
    """Refuse a question with no health and safety signal in it at all.

    The opposite kind of test to the one above: this fires on the ABSENCE of a
    keyword, so a follow-up like "what about on a smaller site?" trips it despite
    being perfectly in scope. That is why answer_question runs this against the
    rewritten question rather than the raw one (issue S3-02).
    """

    if not HEALTH_SAFETY_SIGNAL.search(question.casefold()):
        return (
            "I can only assist with New Zealand workplace health and safety questions. "
            "Please ask a health and safety related question."
        )

    return None


def _preflight_guardrail_answer(question: str) -> Optional[str]:
    """Handle unambiguous scope cases before retrieval can introduce noise."""

    return _intent_refusal(question) or _scope_refusal(question)


def build_condense_chain(llm=None):
    """Create the prompt-to-LLM chain that rewrites a follow-up."""

    if llm is None:
        llm = _get_condense_llm()

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", CONDENSE_QUESTION_PROMPT),
            (
                "human",
                "Conversation so far:\n{transcript}\n\nLatest question: {question}\n\nRewritten question:",
            ),
        ]
    )

    if isinstance(llm, Runnable):
        return prompt | llm

    if hasattr(llm, "invoke"):
        return RunnableLambda(llm.invoke)

    raise TypeError(f"Unsupported LLM type: {type(llm).__name__}")


def condense_question(question: str, history=None, llm=None) -> str:
    """Rewrite a follow-up so it can be retrieved on without the conversation.

    Returns the question untouched when there is no history, which is every first
    question of a conversation. That is the cheap path and the common one: no
    second model call, and behaviour identical to before this existed.

    A failed rewrite falls back to the original question rather than raising. A
    follow-up answered as if it were standalone is a worse answer; a follow-up that
    errors is no answer at all.
    """

    transcript = conversation.as_transcript(history)

    if not transcript:
        return question

    try:
        chain = build_condense_chain(llm=llm)
        response = chain.invoke({"transcript": transcript, "question": question})
        rewritten = response.content if hasattr(response, "content") else str(response)
    except Exception:
        return question

    rewritten = (rewritten or "").strip()

    # A model that decided to explain itself, or returned nothing, is not something
    # to hand to the guardrail — the original question is the safer input.
    if not rewritten or len(rewritten) > 4 * len(question) + 200:
        return question

    return rewritten


def build_answer_chain(llm=None):
    """Create a LangChain prompt-to-LLM chain for grounded answers.

    Earlier turns go in as real user and assistant messages between the system
    prompt and the question, not pasted into the question text. With no history the
    placeholder renders nothing, so a standalone question produces exactly the two
    messages this chain has always produced.
    """

    if llm is None:
        llm = _get_openai_chat_llm()

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", GROUNDING_SYSTEM_PROMPT),
            MessagesPlaceholder("history", optional=True),
            (
                "human",
                "Question: {question}\n\nRetrieved context:\n{context}\n\nAnswer using only the supplied context. Do not include a source list in the answer; the interface renders source citations separately.",
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
                        "history": payload.get("history", []),
                    }
                return llm.invoke(payload)
            return llm.invoke(payload)

        return RunnableLambda(_invoke_with_prompt)

    raise TypeError(f"Unsupported LLM type: {type(llm).__name__}")


def answer_question(
    question: str,
    *,
    history=None,
    retriever_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    llm=None,
    condense_llm=None,
    collection_name: Optional[str] = None,
    n_results: Optional[int] = None,
):
    """Retrieve relevant chunks, ask the LLM for a grounded answer, and return metadata.

    The returned dict carries the retrieved records under "chunks" so a caller
    can show what the answer was actually built from without retrieving again.

    `history` is the conversation so far, oldest first, as {"role", "content"}
    turns. It is owned by the caller's session and only ever read here — nothing
    about a conversation is stored between calls.

    The guardrails run in two halves around the rewrite. What the question asks for
    is judged on the user's own words; whether it is in scope at all is judged on
    the rewritten question, because a follow-up carries its subject in the
    conversation rather than in its own words. With no history the rewrite is a
    no-op and the two halves are simply the original single check.
    """

    if not question or not question.strip():
        raise ValueError("Question cannot be empty")

    intent_refusal = _intent_refusal(question)
    if intent_refusal is not None:
        return {
            "answer": intent_refusal,
            "sources": [],
            "chunks": [],
            "status": "guardrail",
        }

    question = condense_question(question, history=history, llm=condense_llm)

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
        response = chain.invoke(
            {
                "question": question,
                "context": _format_context(results),
                "history": conversation.as_messages(history),
            }
        )
        answer = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        return {
            "answer": "I could not generate an answer because the language model is currently unavailable.",
            "sources": [],
            "chunks": results,
            "status": "error",
            "error": f"OpenAI API error: {exc}",
        }

    cleaned_answer = _strip_inline_citations(answer)

    if _answer_has_no_support(cleaned_answer):
        return {
            "answer": cleaned_answer,
            "sources": [],
            "chunks": [],
            "status": "no_results",
        }

    return {
        "answer": cleaned_answer,
        "sources": _source_metadata(results),
        "chunks": results,
        "status": "ok",
    }
