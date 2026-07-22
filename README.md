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