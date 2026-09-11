# src/api

The FastAPI backend that exposes the RAG pipeline. The frontend sends a user's
question to an API endpoint here; the backend runs retrieval + generation and
returns the answer plus its citation.

Kept separate from the UI so the heavy AI work (ChromaDB, embeddings, LangChain)
is decoupled from the frontend and easier to host, test, and scale.

## Endpoints

| Route | What it does |
|---|---|
| `POST /chat` | Answer a question. Returns `answer`, `sources`, `latency_seconds`, `status`. |
| `POST /ask` | The original name for `/chat`, kept so existing callers keep working. |
| `GET /health` | Readiness check: service status, collection name, stored chunk count and startup time. |

Request and response shapes are pydantic models in `app.py`, defined once and
reused by both routes. The timed pipeline call itself lives in `src/pipeline.py`.

See the README at the repo root for how to start the server and what the JSON
looks like.
