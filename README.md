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

You'll need Python 3.10+ installed.

```bash
# 1. Clone the repo
git clone <repo-url>
cd Health-Saftey-AI

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your API key
cp .env.example .env             # then open .env and paste your OpenAI key
```

Never commit your `.env` file — it holds secret keys. It's already gitignored.

---

## Running the app

The backend (FastAPI) and the frontend (Streamlit) run as two separate
processes. Open two terminals:

```bash
# Terminal 1 — backend API
# (the FastAPI entry point lives in src/api/)

# Terminal 2 — frontend UI
# (the Streamlit app entry point lives in src/ui/)
```

Exact run commands will be added as the code for each part is written.

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
5. Never commit secrets (your `.env` file) or large generated files.
