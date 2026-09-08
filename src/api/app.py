"""FastAPI backend exposing the RAG pipeline over HTTP.

The interface never imports the pipeline: it posts a question here and gets back
a fixed JSON shape — answer, sources, latency_seconds, status. Everything to do
with retrieval and generation happens behind src.pipeline.run_query, and this
module only translates between HTTP and that call.

Start it from the repo root with:  ./scripts/run_api.sh
Then try it at:                    http://localhost:8000/docs
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Union

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from src.answer import _get_openai_chat_llm
from src.config.settings import CHROMA_COLLECTION_NAME, CHROMA_PERSIST_DIR
from src.pipeline import run_query
from src.retrieval.retriever import _get_openai_client
from src.vectorstore_client import count_collection

# Uvicorn configures its own "uvicorn.*" loggers and leaves the root logger at
# WARNING, so without this our INFO lines are silently dropped and only errors
# reach the terminal (via logging's last-resort handler). This module is the
# application entry point, so configuring logging here is its job.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:     %(message)s",
)

logger = logging.getLogger(__name__)


# =====================================================
# STARTUP
# =====================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the vector store and the model clients once, before serving.

    Every client below is cached at its own definition, so calling them here is
    what makes the first question as fast as the second: the cost is paid while
    uvicorn is still starting rather than by whoever asks first.
    """

    started = time.perf_counter()

    chunk_count = count_collection()

    # Refuse to serve rather than answer "I do not have information on that
    # topic" to every question for the rest of the process's life.
    if chunk_count < 1:
        raise RuntimeError(
            f"Collection '{CHROMA_COLLECTION_NAME}' is empty or missing "
            f"({chunk_count} chunks at {CHROMA_PERSIST_DIR}). "
            "Run ingestion to populate the vector store before starting the API."
        )

    # A missing key is not fatal the way an empty collection is: the pipeline
    # already turns it into a structured error, and the team can still read
    # /docs and /health. Loud warning, not a hard stop.
    try:
        _get_openai_client()
        _get_openai_chat_llm()
    except Exception as exc:
        logger.warning(
            "Model clients could not be created at startup, so answers will "
            "fail until this is fixed: %s",
            exc,
        )

    startup_seconds = round(time.perf_counter() - started, 2)

    app.state.collection_name = CHROMA_COLLECTION_NAME
    app.state.chunk_count = chunk_count
    app.state.startup_seconds = startup_seconds

    logger.info(
        "Ready in %ss — collection '%s', %d chunks.",
        startup_seconds,
        CHROMA_COLLECTION_NAME,
        chunk_count,
    )

    yield


app = FastAPI(
    title="Health & Safety AI API",
    description=(
        "Ask a New Zealand workplace health and safety question and get an "
        "answer grounded in the WorkSafe guidance corpus, with the documents "
        "it came from."
    ),
    lifespan=lifespan,
)


# =====================================================
# REQUEST AND RESPONSE MODELS
# =====================================================
# Defined once here and reused by every route, so the shape the interface codes
# against cannot drift between endpoints.


class ChatRequest(BaseModel):
    """A question, and nothing else.

    The collection and top-k are deliberately not part of the HTTP contract.
    They stay as arguments on run_query for tests and scripts: exposing them
    here let the /docs page fill them with placeholders ("string", 0), which
    silently searched an empty collection and returned no results.
    """

    question: str = Field(description="The health and safety question to answer.")

    @field_validator("question")
    @classmethod
    def _reject_blank_question(cls, value: str) -> str:
        """Treat "" and "   " the same, so both get one readable message."""

        if not value or not value.strip():
            raise ValueError("Question cannot be empty.")
        return value


# Kept so anything still importing the old name keeps working.
Query = ChatRequest


class Source(BaseModel):
    """One retrieved chunk's attribution — the locked Sprint 1 metadata schema."""

    source_file: Optional[str] = None
    page_number: Optional[int] = None
    section_heading: Optional[str] = None
    chunk_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[Source]
    latency_seconds: float
    # "ok", "no_results" or "guardrail". The interface uses this to tell a real
    # answer from "nothing relevant was found" without parsing the answer text.
    status: str


class HealthResponse(BaseModel):
    # "ok" when the collection holds chunks, "unavailable" when it does not.
    status: str
    collection_name: str
    chunk_count: int
    # How long startup took. Recorded here so the cold start number does not
    # have to be dug out of the server log.
    startup_seconds: float


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str


# Shown on the /docs page alongside the success schema. The key type matches
# FastAPI's own signature (it allows a status code or a range like "4XX"), which
# a plain Dict[int, ...] is not assignable to.
ERROR_RESPONSES: Dict[Union[int, str], Dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "The question was missing or empty."},
    500: {"model": ErrorResponse, "description": "The pipeline failed."},
}


# =====================================================
# ERROR HANDLING
# =====================================================


def _validation_message(exc: RequestValidationError) -> str:
    """Turn pydantic's error list into one sentence a person can act on."""

    for error in exc.errors():
        if error.get("type") == "missing":
            return "A question is required."
        # Errors raised by our own validators arrive prefixed by pydantic.
        message = str(error.get("msg", "")).removeprefix("Value error, ")
        if message:
            return message

    return "The request could not be read."


@app.exception_handler(RequestValidationError)
async def _handle_validation_error(request: Request, exc: RequestValidationError):
    """Answer a bad request with a readable message instead of a 500."""

    return JSONResponse(
        status_code=422,
        content=ErrorResponse(message=_validation_message(exc)).model_dump(),
    )


def _error_response(message: str, detail: str) -> JSONResponse:
    """Log the technical detail here; send the browser the plain sentence only."""

    logger.error("Pipeline failure: %s", detail)

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(message=message).model_dump(),
    )


# =====================================================
# DEPENDENCIES
# =====================================================


def get_llm():
    """Return a chat LLM, or None so the pipeline reports the failure itself.

    The client itself is cached and warmed at startup, so this is a lookup
    rather than a construction. Tests override this dependency to inject a stub.
    """

    try:
        return _get_openai_chat_llm()
    except Exception:
        # Returning None lets answer_question produce a structured error rather
        # than the whole API failing to serve.
        return None


# =====================================================
# ROUTES
# =====================================================


@app.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "The collection is empty."}},
)
def health():
    """Report whether the backend is ready to answer questions.

    The chunk count is read live rather than served from the startup snapshot,
    so a collection emptied while the server is running is caught. Story 8's
    interface uses this as its readiness check, which only works if it can
    actually go unready.
    """

    chunk_count = count_collection()

    body = HealthResponse(
        status="ok" if chunk_count > 0 else "unavailable",
        collection_name=app.state.collection_name,
        chunk_count=chunk_count,
        startup_seconds=app.state.startup_seconds,
    )

    if chunk_count < 1:
        return JSONResponse(status_code=503, content=body.model_dump())

    return body


@app.post("/chat", response_model=ChatResponse, responses=ERROR_RESPONSES)
@app.post("/ask", response_model=ChatResponse, responses=ERROR_RESPONSES, include_in_schema=False)
def chat(request: ChatRequest, llm=Depends(get_llm)):
    """Answer a health and safety question from the WorkSafe corpus.

    /ask is the original name for this route, kept so nothing that already calls
    it breaks. New callers should use /chat.
    """

    try:
        result = run_query(request.question, llm=llm)
    except Exception as exc:
        return _error_response(
            "Something went wrong while answering that question. Please try again.",
            f"Unhandled exception: {exc!r}",
        )

    if result["status"] == "error":
        return _error_response(
            "Something went wrong while answering that question. Please try again.",
            result.get("error") or "no detail reported",
        )

    return result
