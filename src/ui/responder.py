"""Where the interface gets its answers from.

The one seam between the chat interface and the pipeline. It reaches the RAG
backend over HTTP rather than importing it, which is what keeps ChromaDB,
LangChain and the OpenAI credentials out of the interface process entirely —
the backend is the only component that holds them.

app.py fetches the structured response once, then streams only its answer text.
"""

import logging
import time

import httpx

from src import conversation
from src.config import settings

# Pause between words when replaying an answer, in seconds. The backend returns
# a finished answer rather than a stream, so this replays it at reading speed
# instead of dropping the whole block in at once.
WORD_DELAY = 0.02

logger = logging.getLogger(__name__)

UNAVAILABLE_REPLY = (
    "I could not reach the answering service, so I cannot answer that right "
    "now. Check that the backend is running, then try again."
)
TIMEOUT_REPLY = (
    "That took too long to answer. Please try again, and consider asking a "
    "shorter or more specific question."
)
ERROR_REPLY = (
    "The answering service could not complete that request. Please try again "
    "in a moment."
)
NO_RESULTS_REPLY = (
    "I could not find supporting guidance for that question. Please try "
    "different wording or ask another workplace health and safety question."
)

# Kept for callers that used the old single fallback constant.
FALLBACK_REPLY = UNAVAILABLE_REPLY


def _result(answer, status, sources=None):
    return {"answer": answer, "sources": sources or [], "status": status}


def _health_check():
    """Return whether the backend is ready, without exposing its diagnostics."""

    try:
        response = httpx.get(
            f"{settings.API_BASE_URL}/health",
            timeout=settings.API_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        logger.warning("Backend readiness check timed out: %s", exc)
        return "timeout"
    except httpx.RequestError as exc:
        logger.warning("Backend readiness check failed: %s", exc)
        return "unavailable"

    if response.status_code != 200:
        logger.warning("Backend is not ready (HTTP %s).", response.status_code)
        return "unavailable"

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("Backend readiness response was invalid: %s", exc)
        return "error"

    if not isinstance(payload, dict):
        logger.warning("Backend readiness response had an invalid shape.")
        return "error"

    return "ok" if payload.get("status") == "ok" else "unavailable"


def fetch_reply(question, history=None):
    """Return the backend answer and its source metadata in one request."""
    readiness = _health_check()
    if readiness == "timeout":
        return _result(TIMEOUT_REPLY, "timeout")
    if readiness == "unavailable":
        return _result(UNAVAILABLE_REPLY, "unavailable")
    if readiness != "ok":
        return _result(ERROR_REPLY, "error")

    try:
        response = httpx.post(
            f"{settings.API_BASE_URL}/chat",
            json={
                "question": question,
                "history": conversation.trim(history),
            },
            timeout=settings.API_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        logger.warning("Backend answer request timed out: %s", exc)
        return _result(TIMEOUT_REPLY, "timeout")
    except httpx.RequestError as exc:
        logger.warning("Backend answer request failed: %s", exc)
        return _result(UNAVAILABLE_REPLY, "unavailable")

    if response.status_code != 200:
        logger.warning("Backend answer request returned HTTP %s.", response.status_code)
        return _result(ERROR_REPLY, "error")

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("Backend answer response was invalid: %s", exc)
        return _result(ERROR_REPLY, "error")

    if not isinstance(payload, dict):
        logger.warning("Backend answer response had an invalid shape.")
        return _result(ERROR_REPLY, "error")

    status = payload.get("status", "ok")
    answer = payload.get("answer", "")
    if status == "no_results" and not answer:
        answer = NO_RESULTS_REPLY

    if not isinstance(answer, str) or not isinstance(payload.get("sources", []), list):
        logger.warning("Backend answer response had an invalid shape.")
        return _result(ERROR_REPLY, "error")

    sources = payload.get("sources", []) if status == "ok" else []
    return _result(answer, status, sources)


# The file extension the backend reads the audio format from, by browser MIME type.
# The type can carry a codec suffix ("audio/webm;codecs=opus"), so it is matched on
# the part before the semicolon.
AUDIO_EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
}


def transcribe(audio_bytes, mime):
    """Return {"text", "status"} for a recorded question.

    "ok" carries the transcript, "empty" means nothing was said, and "error" covers
    everything else: an unreachable backend, a timeout, or a failed transcription.
    Nothing here answers the question; the transcript is only shown to the user.
    """

    base_type = (mime or "").split(";")[0].strip().lower()
    extension = AUDIO_EXTENSIONS.get(base_type, "webm")

    try:
        response = httpx.post(
            f"{settings.API_BASE_URL}/transcribe",
            files={"audio": (f"question.{extension}", audio_bytes, base_type or "audio/webm")},
            timeout=settings.API_TIMEOUT_SECONDS,
        )
    except httpx.RequestError:
        return {"text": "", "status": "error"}

    if response.status_code != 200:
        return {"text": "", "status": "error"}

    payload = response.json()
    text = (payload.get("text") or "").strip()

    return {"text": text, "status": "ok" if text else "empty"}


def stream_answer(answer):
    """Yield an already-fetched answer in chunks for Streamlit."""

    for word in answer.split(" "):
        time.sleep(WORD_DELAY)
        yield word + " "


def stream_reply(question, history=None):
    """Backward-compatible answer-only wrapper around :func:`fetch_reply`."""

    yield from stream_answer(fetch_reply(question, history)["answer"])
