# src/ui

The Streamlit chat interface — the ChatGPT-style web app users interact with.

Run it from the repo root, with the backend already running:

```bash
./scripts/run_api.sh               # terminal 1 — backend on :8000
./scripts/run_ui.sh                # terminal 2 — interface on :8501
```

Answers come from the backend's `/chat` endpoint. With it stopped the interface
still runs, but every question returns the "could not reach the answering
service" fallback.

| File          | What it does                                                       |
| ------------- | ------------------------------------------------------------------ |
| `app.py`      | Draws the page: sidebar, conversation, chat input                   |
| `state.py`    | Holds the message history in the browser session                    |
| `responder.py`| Calls the backend over HTTP — the one file that talks to it         |
| `corpus.py`   | Lists the source PDFs under `data/raw/` for the sidebar             |
| `styles.css`  | The ChatGPT-like styling `app.py` loads                             |

`streamlit_app.py` at the repo root is the entry point; it exists there so the
repo root is on `sys.path` and the interface can import from `src/`. Colours and
fonts are set in `.streamlit/config.toml`.

## Kept separate from the pipeline

Nothing here imports ChromaDB, LangChain or the modules under `src/answer.py`,
`src/retrieval/` or `src/embeddings/`. `tests/ui/test_ui_isolation.py` enforces
that, so the interface stays deployable on its own and the backend remains the
only component holding the vector store and credentials.

`responder.py` is the single seam between the interface and whatever answers a
question. It reaches the pipeline over HTTP rather than importing it, which is
what keeps the credentials and the vector store on the backend side.

The backend URL is `API_BASE_URL` in `src/config/settings.py`, overridable with
the `HS_API_BASE_URL` environment variable — `src/config` is the one project
module the interface is allowed to import.
