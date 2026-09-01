"""FastAPI app exposing a simple /ask endpoint for the RAG pipeline.

This is a thin wrapper that calls src.answer.answer_question and returns the
structured response. It accepts an optional dependency to inject an LLM client
for testing or alternative runtime wiring.
"""

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from src.answer import answer_question, _get_openai_chat_llm

app = FastAPI(title="Health & Safety AI API")


class Query(BaseModel):
    question: str
    collection_name: Optional[str] = None
    n_results: Optional[int] = None


def get_llm():
    """Dependency that returns a Chat LLM instance or None on construction error.

    Tests can override this dependency to provide a stub.
    """
    try:
        return _get_openai_chat_llm()
    except Exception:
        # Let answer_question report the error in a structured way instead
        # of causing the whole API to fail at startup.
        return None


@app.post("/ask")
def ask(query: Query, llm=Depends(get_llm)):
    try:
        result = answer_question(
            query.question, llm=llm, collection_name=query.collection_name, n_results=query.n_results
        )

        # Normalise unexpected failure modes into HTTP 500 so clients see a
        # clear status code while the body contains the structured error.
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result)

        return result
    except HTTPException:
        raise
    except Exception as exc:
        # Fallback: unexpected error
        raise HTTPException(status_code=500, detail={"status": "error", "error": str(exc)})
