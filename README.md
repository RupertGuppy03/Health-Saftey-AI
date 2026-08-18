# Health & Safety AI — Compliance Chatbot

A Retrieval-Augmented Generation (RAG) chatbot that helps New Zealand small and
medium businesses understand and apply workplace health & safety requirements.
Users ask questions in plain language and get accurate, NZ-specific guidance
grounded in official sources (WorkSafe NZ + the Health and Safety at Work Act
2015), with citations back to the source document and page. It also identifies
workplace hazards from a description and suggests mitigation strategies.

See [`PROJECT-BREIF.md`](PROJECT-BREIF.md) for the full project brief.

---

## Tech stack

- **Python** throughout
- **OpenAI API** (GPT-4o) as the LLM, plus OpenAI embeddings
- **LangChain** for orchestration
- **ChromaDB** as the vector store (persisted to disk)
- **PyMuPDF / pdfplumber** for PDF text extraction
- **FastAPI** backend (the RAG pipeline), decoupled from...
- **Streamlit** frontend (the chat UI)
- **pytest** for unit tests, **DeepEval** for AI evaluation
- **Docker** for containerising the backend
- **GitHub** for version control

---

## Getting started (local setup)

This project runs on **Python 3.14**. First, check you have it:

```bash
python3 --version        # should print 3.14.something
```

If it doesn't, install Python 3.14 from [python.org](https://www.python.org/downloads/)
(or with `pyenv`), then continue.

Now copy-paste these commands one block at a time:

```bash

# 1. Create a private space for this project's packages
python3 -m venv .venv

# 2. Switch that space on
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install everything the project needs (exact, tested versions)
pip install -r requirements.txt
```

That's it — the project is installed. ✅

### 4. Environment variables

Copy `.env.example` to `.env` and fill in the real values. `.env` is gitignored and
must never be committed.

| Variable | Used by | Purpose |
|---|---|---|
| `OPEN_AI_API_KEY` | `src/embeddings/chunking_script_v2.py` | OpenAI key for generating embeddings |
| `UNSTRUCTURED_API_KEY` | `src/ingestion/extract.py` | Unstructured API key for PDF extraction |
| `UNSTRUCTURED_API_URL` | `src/ingestion/extract.py` | Unstructured API endpoint |

Note on the key name: this project uses `OPEN_AI_API_KEY`, but the OpenAI SDK looks for
`OPENAI_API_KEY` by default. The code accepts **either**, so you don't need to change an
existing `.env`.

---

---

## Folder map

| Folder          | What's in it                                              |
| --------------- | --------------------------------------------------------- |
| `data/`         | Source PDFs (`raw/`) and cleaned text (`processed/`)      |
| `vectorstore/`  | The persisted ChromaDB embeddings (not committed to git)  |
| `references/`   | User stories and planning docs, grouped by sprint         |
| `notebooks/`    | Personal experiments and scratch work                     |
| `tests/`        | Automated tests (`pytest`) and AI evaluations (`eval/`)   |
| `src/`          | All the application source code                            |
| `scripts/`      | One-command runners (e.g. ingest all docs, run evals)     |

Each folder has its own short `README.md` explaining what belongs in it.

---

## Working together

We collaborate on GitHub. To keep things simple and avoid clashes:

1. Always start from an up-to-date `main` branch.
2. Create your own branch for the work you're doing.
3. Work in your area of the project.
4. Open a Pull Request when you're ready, so the team can review before it
   merges into `main`.

---

## ChromaDB persistence (vectorstore)

This project uses ChromaDB as a local, on-disk vector store. The persisted files live
under the repository root in the `vectorstore/` folder and are intentionally not
committed to git.

Why not commit the vectorstore?

- The persisted embeddings are large and binary; they don't suit diffs or code review.
- Vector stores are environment-specific and can be rebuilt by ingestion when needed.

How to inspect the persisted collection locally

After installing the project's dependencies (see "Getting started"), run the
verification script which opens the named collection defined in code and prints
its item count (works even when the collection is empty):

```bash
python scripts/check_chroma_collection.py
```

The collection name is defined centrally in `src/config/settings.py` as
`CHROMA_COLLECTION_NAME`. To open a different collection name for debugging pass
`--collection NAME` to the script.

## Embeddings

Configured centrally in `src/config/settings.py`:

| Setting | Value | Notes |
|---|---|---|
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Must be the same at ingestion and query time |
| `EMBEDDING_DIMENSIONS` | `1536` | The model's native width; not truncated |
| `EMBEDDING_BATCH_SIZE` | `128` | Texts per API call — the full corpus is ~43 calls, not ~5,400 |
| `EMBEDDING_MAX_TOKENS_PER_REQUEST` | `100000` | A batch over this is split again |
| `PIPELINE_VERSION` | `2.0.0` | Stamped on every record; bump when a change invalidates stored vectors |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `4000` / `800` | Characters, not tokens; stamped alongside each record |

Embedding the whole corpus (~5,400 chunks) costs roughly **$0.02**.

**Querying the collection:** the stored vectors are 1536-dimension OpenAI vectors, but
ChromaDB still has its own built-in 384-dimension embedder attached. Calling
`collection.query(query_texts=...)` would use that built-in model and fail with a
dimension mismatch. Always embed the query yourself and pass `query_embeddings=`:

```python
from src.embeddings.chunking_script_v2 import embed_texts
from src.vectorstore_client import get_collection

vector = embed_texts(["your question here"])
results = get_collection().query(query_embeddings=vector, n_results=5)
```

## Re-running ingestion and rebuilding

Ingestion is safe to re-run. Every chunk gets a deterministic ID built from the
document filename, its page number and its position in the document, so a repeat run
overwrites the same records instead of appending duplicates.

Each record also stores the pipeline that produced it: `pipeline_version`,
`embedding_model`, `chunk_size` and `chunk_overlap`. That is how you tell whether a
vector in the collection is stale.

**When re-ingesting the document is enough.** If you change chunking or cleaning and
re-ingest a document, any record the new run no longer produces is deleted. A document
that used to yield 500 chunks and now yields 300 ends up with exactly 300 — the 200
leftovers are removed rather than left behind to be retrieved later. This happens
automatically; you do not need to clear anything first.

**When you must rebuild everything.** Changing the embedding model, or its dimensions,
invalidates every vector in the collection, and mixing widths in one collection is an
error. Bump `PIPELINE_VERSION` and wipe the collection:

```python
from src.vectorstore_client import reset_collection

reset_collection()   # drops and recreates hs_construction_v1, empty
```

Then re-ingest every document. A full re-embed of the corpus is roughly 5,400 chunks,
about 43 API calls and around $0.02, so rebuilding is cheap — when in doubt, rebuild.

To keep the old vectors around for comparison, change `CHROMA_COLLECTION_NAME` in
`src/config/settings.py` to a new version (for example `hs_construction_v2`) instead of
resetting, and ingest into that.

