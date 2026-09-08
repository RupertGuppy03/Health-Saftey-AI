"""FastAPI backend exposing the RAG pipeline over HTTP.

The interface never imports the pipeline: it posts a question here and gets back
a fixed JSON shape — answer, sources, latency_seconds, status. Everything to do
with retrieval and generation happens behind src.pipeline.run_query, and this
module only translates between HTTP and that call.

Start it from the repo root with:  ./scripts/run_api.sh
Then try it at:                    http://localhost:8000/docs
"""

import logging
from typing import Any, Dict, List, Optional, Union

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from src.answer import _get_openai_chat_llm
from src.pipeline import run_query

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Health & Safety AI API",
    description=(
        "Ask a New Zealand workplace health and safety question and get an "
        "answer grounded in the WorkSafe guidance corpus, with the documents "
        "it came from."
    ),
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

    Constructed per request for now; story 2 moves this to application startup.
    Tests override this dependency to inject a stub.
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
