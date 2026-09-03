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

## Running local checks and tests

A small helper script avoids the common "python: command not found" issue on systems that expose only `python3`. It runs a quick import smoke-check using `python3` when available.

- Run the smoke check:

    ./scripts/run_local_checks.sh

- Run the retrieval→LLM unit tests (added for US-06):

    python3 -m pytest tests/test_answer_chain.py -q

Make sure your `.env` contains `OPEN_AI_API_KEY` or `OPENAI_API_KEY` before running any tests that call the OpenAI API. The code accepts either name.

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

## Running the chat interface

```bash
streamlit run streamlit_app.py     # or: ./scripts/run_ui.sh
```

The backend does **not** need to be running. Answers currently come from a
placeholder in `src/ui/responder.py`, so the interface can be built and reviewed
while the RAG pipeline is being finished. Story 4 replaces that placeholder with
an HTTP call to the FastAPI backend.

The sidebar lists every source PDF under `data/raw/`; a document is only read
from disk when someone clicks it.

Colours, fonts and radii are set in `.streamlit/config.toml`, which defines a
light and a dark palette. The interface follows whichever theme the viewer has
picked under the ⋮ menu → Settings → Appearance. No environment variables or API
keys are needed to run it.

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
| `src/ui/`       | The Streamlit chat interface (run `streamlit_app.py`)      |
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
| `PIPELINE_VERSION` | `3.0.0` | Stamped on every record; bump when a change invalidates stored vectors |
| `CHUNK_TARGET_CHARS` | `3000` | What the packer aims for per chunk (~750 tokens, inside the locked 500-1000 band) |
| `CHUNK_MAX_CHARS` | `4000` | Hard ceiling for a single chunk |
| `CHUNK_MIN_CHARS` | `300` | A chunk below this is folded into a neighbour rather than stored on its own |
| `CHUNK_OVERLAP_CHARS` | `600` | Trailing context carried into the next prose chunk |
| `HEADING_STRUCTURAL_SHARE` | `0.40` | Threshold for whether a document's headings are numbered/ALL-CAPS enough to trust on their own |

Embedding the whole corpus (~3,700 chunks) costs a fraction of a cent.

### How chunking works

Cleaned elements are packed **in document order** into chunks — not split from a single
joined string, the way a text splitter works. `Title` elements are candidate section
breaks, `Table` elements are always their own chunk, and everything else accumulates
until a chunk is worth retrieving.

Not every `Title` element extracted from a PDF is a real heading — line-wrapped text is
sometimes tagged `Title` element by element, which would turn a broken sentence into a
string of one-word "section headings" and one-line "chunks". Two checks catch this:

- **Structural test**: numbered (`1.3`, `2.1`) or short ALL CAPS text is always trusted
  as a heading, regardless of context.
- **Shape test**: a short, capitalised, non-numbered line (e.g. `Key terms`) is trusted
  as a heading only if it is not a Title Case document's house style *and* the previous
  element reads as a finished sentence. Without that second condition, a capitalised
  line-wrap fragment (e.g. `"Work Act 2015 (HSWA), illustrate different"`, itself a
  continuation of the previous line) would be mistaken for a new heading.

Which documents get the shape test is decided **per document**: `detect_allow_heading_shape`
measures what share of a document's own `Title` elements are structural, and only enables
the looser shape rule where the document does not already have a clear numbered/ALL-CAPS
convention (below `HEADING_STRUCTURAL_SHARE`). Both checks are purely typographic — they
never look at subject matter, so behaviour does not depend on which topic a document covers.

A misclassified heading only costs a slightly less precise `section_heading` in a
citation — it never creates its own tiny chunk, since a heading always attaches to the
body text that follows it.

Tables are never split below their size cap and never merged with surrounding prose.
Where a heading-only label sits directly before a table with nothing to merge it
backward into (a checklist-style `Label` → `Table` → `Label` → `Table` run), the label is
prepended to the table as a caption instead of being left as its own one-line chunk. A
table larger than `CHUNK_MAX_CHARS` is split on row boundaries, and the header row is
repeated at the top of every part so each stands alone.

A small number of chunks (well under 1% of the corpus) remain under `CHUNK_MIN_CHARS` —
mainly a trailing heading at the very end of a document with a table immediately before
it and nothing after. This is accepted rather than fixed by relaxing "tables are never
merged with prose".

**Querying the collection:** use `src/retrieval/retriever.py` — see
[Retrieval](#retrieval) below. Do not call `collection.query(query_texts=...)`
directly; the reason is explained there.

## Retrieval

Turning a user's question into the chunks that answer it. One function:

```python
from src.retrieval import retriever

results = retriever.retrieve("What edge protection is needed on a roof?")
print(retriever.format_results(results))
```

Each result is a plain dict:

| key | what it is |
| --- | --- |
| `rank` | 1-based position, nearest first |
| `chunk_id` | the deterministic ingestion ID, e.g. `working-on-roofs-GPG:p0004:0012` |
| `text` | the chunk itself |
| `source_file`, `page_number`, `section_heading` | the locked Sprint 1 metadata — this is what a citation is built from |
| `chunk_type` | `prose`, `table`, `appendix` or `glossary`; `None` if the record has none |
| `distance` | how far the chunk is from the question; smaller is nearer |

**How many chunks come back** is `RETRIEVAL_TOP_K` in `src/config/settings.py`,
currently **6**. That is the single source of truth — retrieval, the terminal
script and the eval runs all read it rather than each passing their own number.
Override it for one call with `retrieve(question, n_results=4)`.

**The query is embedded with `EMBEDDING_MODEL`**, the same model used at
ingestion and read from the same place in settings. A query embedded any other
way is not comparable to what is stored and returns meaningless neighbours.

**Never pass `query_texts=`.** The stored vectors are 1536-dimension OpenAI
vectors, but ChromaDB still has its own built-in 384-dimension embedder
attached, and `query_texts=` would use it and fail on a dimension mismatch.
`retrieve()` embeds the question itself and passes `query_embeddings=`.

Retrieval only reads. It never writes to the collection and never re-embeds a
document — the only thing it sends to OpenAI is the question.

To see it working across five documents, run `notebooks/S2_retrieval.ipynb`.

## Re-running ingestion and rebuilding

Ingestion is safe to re-run. Every chunk gets a deterministic ID built from the
document filename, its page number and its position in the document, so a repeat run
overwrites the same records instead of appending duplicates.

Each record also stores the pipeline that produced it: `pipeline_version`,
`embedding_model`, `chunk_target_chars` and `chunk_overlap_chars`. That is how you tell
whether a vector in the collection is stale.

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

Then re-ingest every document. A full re-embed of the corpus is roughly 3,700 chunks and
well under a cent, so rebuilding is cheap — when in doubt, rebuild.

To keep the old vectors around for comparison, change `CHROMA_COLLECTION_NAME` in
`src/config/settings.py` to a new version (for example `hs_construction_v2`) instead of
resetting, and ingest into that.

