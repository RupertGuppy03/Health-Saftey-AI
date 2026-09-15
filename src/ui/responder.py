"""Where the interface gets its answers from.

The one seam between the chat interface and the pipeline. It reaches the RAG
backend over HTTP rather than importing it, which is what keeps ChromaDB,
LangChain and the OpenAI credentials out of the interface process entirely —
the backend is the only component that holds them.

app.py fetches the structured response once, then streams only its answer text.
"""

import time

import httpx

from src import conversation
from src.config import settings

# Pause between words when replaying an answer, in seconds. The backend returns
# a finished answer rather than a stream, so this replays it at reading speed
# instead of dropping the whole block in at once.
WORD_DELAY = 0.02

# Shown when the backend cannot be reached or fails. Deliberately plain: story 8
# owns real error handling, the readiness check and the loading indicator, and
# replaces this with messages that distinguish the failures from each other.
FALLBACK_REPLY = (
    "I could not reach the answering service, so I cannot answer that right "
    "now. Check that the backend is running, then try again."
)


def fetch_reply(question, history=None):
    """Return the backend answer and its source metadata in one request.

    `history` is the conversation so far from this browser session's state. It is
    sent with the question so a follow-up can be understood, and it goes no
    further than this request: the backend keeps none of it, so one session's
    conversation cannot appear in another's.
    """
    try:
        response = httpx.post(
            f"{settings.API_BASE_URL}/chat",
            json={
                "question": question,
                "history": conversation.trim(history),
            },
            timeout=settings.API_TIMEOUT_SECONDS,
        )
    except httpx.RequestError:
        return {"answer": FALLBACK_REPLY, "sources": [], "status": "error"}

    # A 200 carries a user-facing answer whether the pipeline answered it, found
    # nothing, or refused it as out of scope, so all three render the same way.
    # Anything else is a validation or server error whose message is written for
    # a developer, not for whoever is asking the question.
    if response.status_code != 200:
        return {"answer": FALLBACK_REPLY, "sources": [], "status": "error"}

    payload = response.json()
    return {
        "answer": payload.get("answer", ""),
        "sources": payload.get("sources", []),
        "status": payload.get("status", "ok"),
    }


def stream_answer(answer):
    """Yield an already-fetched answer in chunks for Streamlit."""

    for word in answer.split(" "):
        time.sleep(WORD_DELAY)
        yield word + " "


def stream_reply(question, history=None):
    """Backward-compatible answer-only wrapper around :func:`fetch_reply`."""

    yield from stream_answer(fetch_reply(question, history)["answer"])
