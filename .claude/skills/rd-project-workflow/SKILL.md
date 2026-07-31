---
name: rd-project-workflow
description: The per-story workflow for the Health & Safety AI (R&D Project) — the NZ WorkSafe RAG compliance chatbot. Use this whenever picking up, building, or planning any user story (US-01 … US-XX) from references/Project_User_Stories.md, or when the user mentions working on a Sprint 1–6 feature, the document/extraction/chunking pipeline, embeddings/ChromaDB, retrieval, the FastAPI backend, or the Streamlit UI for this project — even if they don't name the workflow explicitly. Walks from reading the story through plan, build, explain, test, DoD check, and handing off for the user to commit.
---

# R&D Project Workflow — Health & Safety AI

Apply when picking up any user story on the Health & Safety AI project (a Retrieval-Augmented
Generation compliance chatbot grounded in NZ WorkSafe guidance and the Health and Safety at
Work Act 2015). One story at a time, from reading it to handing off a tested feature the user
commits to their branch.

## Source of truth

- `PROJECT-BREIF.md` — the project brief / "big picture" doc. Read it to understand where the
  feature sits in the whole pipeline before designing. If a `CLAUDE.md` exists, read it too and
  use the two together; a `CLAUDE.md` hasn't been created yet, so until it exists the brief is
  the main project-level reference.
- `references/Project_User_Stories.md` — the master story library (US-01 …). Each story's
  **Acceptance Tests + Definition of Done are the contract.** Don't invent extra scope.
- `references/Sprint_1_and_2_Best_Practices.md` — the guidance each story's `Best Practices:`
  line points at. It holds the *how/why* the acceptance tests assume (e.g. hybrid extraction,
  chunk sizing, what not to strip).
- `references/sprint0/` … `references/sprint6/` — per-sprint context/READMEs.

## Steps

1. **Read the story — and whatever it points to.** Open `references/Project_User_Stories.md`
   and find the US-XX in question. If the story references another document — its
   `Best Practices:` pointer into `Sprint_1_and_2_Best_Practices.md`, or any other linked doc —
   **read that section too**, because that's where the reasoning behind the acceptance tests
   lives. Also read `PROJECT-BREIF.md` for whole-project context. Then quote the story's
   Acceptance Tests + Definition of Done back to the user so you both agree on scope before
   designing anything.

2. **Plan.** Enter plan mode. Propose the file paths (under `src/...` and matching tests under
   `tests/...`), function signatures, key design decisions, and the list of tests you'll write.
   Use AskUserQuestion for any genuine ambiguity (locked parameters, edge cases, file
   conventions) rather than guessing. Don't write code until the user approves and exits plan
   mode.

3. **Build — one story at a time.** Write the feature and its tests. Follow the existing
   codebase: the `src/` layout (`ingestion`, `embeddings`, `retrieval`, `api`, `ui`, `config`),
   paths/settings read from `src/config/` rather than hard-coded, `tests/` mirroring `src/`, and
   the surrounding code's naming and comment style (keep comments brief). Don't drift into the
   next story before this one is done and committed.

4. **Explain plainly.** Give the user a brief, plain-language summary of what you built — plain
   terms, no jargon, **no more than 100 words.** Say which files you created or changed and what
   each one does, so a groupmate could follow it.

5. **Tests — you write them, the user runs them.** Write `pytest` tests that assert the story's
   Acceptance Tests (AI-quality evaluations go in `tests/eval/` with DeepEval — Sprint 2+ work).
   Do **not** run `pytest` yourself; the user runs it to verify and reports the result back. If
   something fails, debug it together — never claim a test passes on your own.

6. **Definition of Done check.** Once the tests are green, walk **every bullet** of the story's
   Definition of Done out loud. Flag anything missing — an artifact not produced, config not
   updated, a downstream file left untouched, the metadata contract not honoured. Resolve it
   before declaring the story done.

7. **Hand off for commit.** The user controls git. Once the tests pass and they're happy, *they*
   commit the feature to their branch so they can showcase it to their groupmates for approval.
   Propose a short, sentence-case commit message matching the style in `git log`. Do **not** run
   git yourself.

## Rules to enforce

- **The user controls git.** Read-only git commands are fine; never commit, push, reset, or
  create branches on their behalf.
- **One story at a time.** Don't start the next story until this one is tested, DoD-checked, and
  committed.
- **The Acceptance Tests + DoD are the agreed contract for the story you're building.** Don't add
  or drop scope on your own while building it.
- **User stories are guidelines, not fixed.** They can be changed when they're wrong or need
  refining — but only after asking the user first and getting agreement. Never silently rewrite a
  story's scope, acceptance tests, or Definition of Done.
- **Locked pipeline decisions** (from the best-practices doc — don't quietly change them):
  - Extraction is **hybrid**: PyMuPDF for prose, pdfplumber for tables — not one or the other.
  - Chunks target **500–1000 tokens** (default 1000) with **100–200 token overlap** (default
    200), split on section headings, tables kept intact as a single chunk.
  - Chunk metadata schema is **`source_file`, `page_number`, `section_heading`, `chunk_type`**
    (US-09). Sprint 2 citations depend on it — keep it consistent across the pipeline.
  - **Never manually trim PDFs.** Clean programmatically; retain appendices, tables, warning
    boxes, glossaries, and legislative references.
- **`tests/` mirrors `src/`.** Use `pytest`; keep DeepEval evaluations in `tests/eval/`.
