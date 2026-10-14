# src/api

The FastAPI backend that exposes the RAG pipeline. The frontend sends a user's
question to an API endpoint here; the backend runs retrieval + generation and
returns the answer plus its citation.

Kept separate from the UI so the heavy AI work (ChromaDB, embeddings, LangChain)
is decoupled from the frontend and easier to host, test, and scale.

## Endpoints

| Route | What it does |
|---|---|
| `POST /chat` | Answer a question. Returns `answer`, `sources`, `latency_seconds`, `citation_present`, `dag_score`, `dag_status`, and `status`. |
| `POST /ask` | The original name for `/chat`, kept so existing callers keep working. |
| `GET /health` | Readiness check: service status, collection name, stored chunk count and startup time. |

Request and response shapes are pydantic models in `app.py`, defined once and
reused by both routes. The timed pipeline call itself lives in `src/pipeline.py`.

For grounded answers, the backend runs DeepEval's `DAGMetric` against the
returned citation source/page metadata and the retrieved chunks. Judge failures
are logged and reported as `dag_status: "unavailable"` while preserving the
answer. Refusals and no-result responses use `dag_status: "not_scored"`.
`HS_DAG_JUDGE_MODEL` selects the judge model (default `gpt-4.1`), and
`HS_API_TIMEOUT_SECONDS` controls how long the interface waits for generation
plus citation scoring (default 240 seconds). Scoring each answer adds an LLM
call, latency, and API cost.

See the README at the repo root for how to start the server and what the JSON
looks like.
