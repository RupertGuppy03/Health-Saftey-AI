# src/ui

The Streamlit chat interface — the ChatGPT-style web app users interact with.

Run it from the repo root:

```bash
streamlit run streamlit_app.py     # or: ./scripts/run_ui.sh
```

The backend does not need to be running. Answers currently come from a
placeholder, so the layout can be built and reviewed while the RAG pipeline is
still being finished.

| File          | What it does                                                       |
| ------------- | ------------------------------------------------------------------ |
| `app.py`      | Draws the page: sidebar, conversation, chat input                   |
| `state.py`    | Holds the message history in the browser session                    |
| `responder.py`| **Placeholder.** Where answers come from — the one file that changes |
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
question. Story 4 replaces the body of `stream_reply` with an HTTP call to the
FastAPI `/chat` endpoint; nothing else in this folder changes.
