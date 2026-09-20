# src/ui

The Streamlit chat interface — the ChatGPT-style web app users interact with.

Run it from the repo root, with the backend already running:

```bash
./scripts/run_api.sh               # terminal 1 — backend on :8000
./scripts/run_ui.sh                # terminal 2 — interface on :8501
```

Answers come from the backend's `/chat` endpoint. With it stopped the interface still runs and shows a plain-language
"could not reach the answering service" message. Slow requests show a separate
timeout message that invites the user to retry.

| File          | What it does                                                       |
| ------------- | ------------------------------------------------------------------ |
| `app.py`      | Draws the page: sidebar, conversation, citations, and chat input     |
| `state.py`    | Holds message text and source metadata in the browser session        |
| `browser_store.py` | Copies the conversation into the browser tab so a reload keeps it |
| `voice.py`    | Handles a recorded question: nothing heard, failed, or a transcript for the chat box |
| `voice.js`    | The mic button, the recording and the live waveform in the chat bar   |
| `responder.py`| Calls the backend and preserves answer source metadata               |
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
the `HS_API_BASE_URL` environment variable. `API_TIMEOUT_SECONDS` controls the
readiness and answer request timeout. Set it with `HS_API_TIMEOUT_SECONDS` before
starting the interface. These settings are the one project module
the interface is allowed to import.

Each successful backend response stores its source metadata with the assistant
message. The page renders citations separately from the answer, grouping
retrieved chunks by document and section and formatting stored filenames into
readable document titles.

## Surviving a reload

Streamlit session state is lost on a page reload, because a reload opens a new
session. `browser_store.py` keeps a copy of the conversation in the tab's
`sessionStorage` and reads it back when the new session starts, so a refresh
brings the conversation back. Nothing is stored on the server: the copy belongs
to that tab and is gone when the tab is closed, and Clear conversation empties
it too. A reload while a reply is still streaming loses that last question,
because the copy is written once each run finishes.

## Voice input

The mic button on the left of the chat bar records a question. While it records,
a waveform fills the bar and moves with your voice; tap the mic again or press
Enter to stop. The recording is transcribed by the backend's `POST /transcribe`
and the transcript is put in the chat box. **Nothing is sent until you press
Enter**, so a mistake can be corrected first, and the question then goes through
`/chat` exactly as if it had been typed.

A recording that is too short or silent is reported as nothing heard without
calling the backend. A failed transcription, or a mic the browser will not open,
is reported plainly, and typing keeps working.

`voice.js` attaches the button to Streamlit's chat bar by its `data-testid`
attributes, so a Streamlit upgrade that renames them would need a matching change
there. pytest cannot run the JavaScript: `tests/ui/test_app.py` replaces the
component with a fake, and the button and waveform are checked in the browser.
