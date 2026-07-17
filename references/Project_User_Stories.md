# Project User Stories — Master Source of Truth

This file is the single source of truth for all user stories on the Health &
Safety AI project. Add and maintain the full list of user stories here.

Detailed, per-story planning is organised by sprint in the `sprint0/` … `sprint6/`
folders alongside this file. See [`../PROJECT-BREIF.md`](../PROJECT-BREIF.md) for
the overall project brief and sprint goals.

<!-- Add user stories below. -->

# User Stories

## Sprint 1

### US-01: Identify required health and safety documents

**Feature:** Document Sourcing & Preparation | **Sprint:** 1 | **Status:** Developing

> As a system designer, I want to identify relevant WorkSafe NZ and legislation documents so that the system uses correct and trusted sources.

**Tasks:**

- Review the WorkSafe NZ publications hub for construction good-practice guides
- Identify the construction-related PDFs (target ~20 guides)
- Select the Health and Safety at Work Act 2015
- Identify relevant codes of practice / regulations
- Compile a written v1 document list and confirm it with the team lead

**Acceptance Tests:**

- [ ] Given the WorkSafe NZ publications hub and NZ legislation, when sourcing is complete, then a written v1 document list exists that names each document with its source URL and its version / publication date.
- [ ] Given the v1 document list, when it is reviewed, then it includes the Health and Safety at Work Act 2015 and the construction good-practice guides (approximately 20 documents).
- [ ] Given the completed list, when it is presented to the team lead, then the team lead has signed off on it (recorded in the list or the PR).

**Definition of Done:**

- [ ] The v1 document list is committed to the repo (e.g. a documents manifest in `references/` or `data/`).
- [ ] Each entry records the document title, source URL, and version / publication date for traceability.
- [ ] The team lead has confirmed the list.
- [ ] Change is committed on a branch and merged via PR.

**Best Practices:** See `Sprint_1_and_2_Best_Practices.md` § "Key Principle: Don't Manually Trim Documents" and §1 Document Sourcing.

---

### US-02: Download resource documents

**Feature:** Document Sourcing & Preparation | **Sprint:** 1 | **Status:** Developing

> As a team member, I want to download all required documents so that they are available locally for processing.

**Tasks:**

- Download the WorkSafe NZ construction PDFs from the v1 list (US-01)
- Download the legislation documents (Health and Safety at Work Act 2015)
- Verify each file opens as a valid PDF
- Store the files in the raw data folder, keeping original filenames

**Acceptance Tests:**

- [ ] Given the v1 document list, when downloading is complete, then every document on the list has a corresponding file saved under `data/raw/`.
- [ ] Given a downloaded file, when it is opened, then it renders as a valid, non–zero-byte PDF (no truncated or corrupted downloads).
- [ ] Given the downloaded files, when they are inspected, then the original filenames are preserved and no file has been converted to another format.
- [ ] Given the raw folder, when checked against the list, then a record maps each downloaded file back to its source URL.

**Definition of Done:**

- [ ] All v1 documents are present under `data/raw/` with original filenames.
- [ ] Every file has been confirmed to open as a valid PDF.
- [ ] A file-to-source-URL record exists (extends the US-01 manifest).
- [ ] Change is committed on a branch and merged via PR (PDFs stored per repo policy, not as untracked large files elsewhere).

**Best Practices:** See `Sprint_1_and_2_Best_Practices.md` §1 Document Sourcing (keep original filenames; do not rename or convert; no trimming at this stage).

---

### US-03: Organise document structure

**Feature:** Document Sourcing & Preparation | **Sprint:** 1 | **Status:** Backlog

> As a developer, I want a structured document system so that files are easy to manage and process.

**Tasks:**

- Confirm the raw input folder `data/raw/`
- Confirm the processed output folder `data/processed/`
- Confirm the reference/docs location `references/`
- Move files into the correct folders
- Keep the README folder map accurate

**Acceptance Tests:**

- [ ] Given the repo, when the structure is set up, then `data/raw/`, `data/processed/`, and `references/` all exist and are used for their intended purpose (raw PDFs, processed text, planning/reference docs).
- [ ] Given the downloaded PDFs, when the structure is applied, then every raw PDF sits under `data/raw/` and no source PDF is left loose elsewhere in the repo.
- [ ] Given the README folder map, when it is checked, then it accurately describes the folders that actually exist in the repo.

**Definition of Done:**

- [ ] The folder structure matches the real repo layout (`data/raw/`, `data/processed/`, `references/`).
- [ ] All files are in their correct folders.
- [ ] The README folder map reflects reality.
- [ ] Change is committed on a branch and merged via PR.

**Best Practices:** See `Sprint_1_and_2_Best_Practices.md` §1 Document Sourcing.

> Note: this story previously referenced `/data/raw_documents`, `/data/processed_documents`, and `/docs/reference`. Those folders do not exist — the repo uses `data/raw/`, `data/processed/`, and `references/`. The story has been updated to the real layout.

---

### US-04: Select v1 core document set

**Feature:** Document Sourcing & Preparation | **Sprint:** 1 | **Status:** Backlog

> As a team, we want to define a minimal document set so that we can start development quickly without unnecessary complexity.

**Tasks:**

- Review all collected documents
- Decide, per document, whether to include or exclude it from the v1 corpus
- Record a one-line rationale for each include / exclude decision
- Finalise the v1 dataset and confirm it with Theo (H&S lead)

**Acceptance Tests:**

- [ ] Given all collected documents, when the v1 set is defined, then it is a labelled subset of the US-01 list with a one-line rationale for each document's inclusion or exclusion.
- [ ] Given the selection process, when it is reviewed, then the only manual decision made was whether to include or exclude a whole document — no pages, sections, or appendices were trimmed inside any document.
- [ ] Given the finalised v1 set, when it is presented to Theo (H&S lead), then Theo has confirmed it.

**Definition of Done:**

- [ ] A documented v1 dataset exists (labelled subset of the US-01 list) with per-document rationale.
- [ ] Excluded documents are marked out-of-scope for v1, not deleted.
- [ ] Theo (H&S lead) has confirmed the final set.
- [ ] Change is committed on a branch and merged via PR.

**Best Practices:** See `Sprint_1_and_2_Best_Practices.md` § "Key Principle: Don't Manually Trim Documents" and §1 Document Sourcing.

---

### US-05: Set up PDF text extraction tool

**Feature:** Document Processing Pipeline | **Sprint:** 1 | **Status:** Backlog

> As a developer, I want to set up a PDF extraction library so that I can extract text from safety documents.

**Tasks:**

- Install **both** PyMuPDF (prose) and pdfplumber (tables) — a hybrid extraction setup
- Test PyMuPDF prose extraction on a sample PDF
- Test pdfplumber `extract_tables()` on a page known to contain a table
- Confirm both produce usable output

**Acceptance Tests:**

- [ ] Given the project environment, when the extraction libraries are installed, then both PyMuPDF and pdfplumber import successfully with no dependency errors.
- [ ] Given a sample WorkSafe PDF, when PyMuPDF's extraction is called on a prose page, then it returns a non-empty string of readable text.
- [ ] Given a multi-page PDF, when PyMuPDF extracts text, then it returns text from all pages, not just the first.
- [ ] Given a page that contains a table, when pdfplumber's `extract_tables()` is called, then it returns the table with row and column structure preserved (not merged into single lines).

**Definition of Done:**

- [ ] Both libraries are declared in `requirements.txt` and import cleanly in the project environment.
- [ ] A short spike / test in `tests/` (or a notebook referenced from it) demonstrates PyMuPDF prose output and pdfplumber table output on real sample PDFs.
- [ ] Extraction settings/paths read from `src/config/` rather than being hard-coded.
- [ ] Change is committed on a branch and merged via PR.

**Best Practices:** See `Sprint_1_and_2_Best_Practices.md` §2 Text Extraction (hybrid PyMuPDF + pdfplumber approach — PyMuPDF is not either/or with pdfplumber).

---

### US-06: Extract raw text from PDFs

**Feature:** Document Processing Pipeline | **Sprint:** 1 | **Status:** Backlog

> As a system, I want to extract text from PDFs so that document content can be processed.

**Tasks:**

- Load PDFs from `data/raw/`
- Extract text page by page (so page numbers can be attached)
- Route table pages to pdfplumber and render tables row-by-row with headers
- Rejoin words split by hyphenated line breaks
- Flag pages that return no text (possible image-only / scanned pages)
- Store raw extracted text and log the source filename

**Acceptance Tests:**

- [ ] Given a folder of raw PDFs, when the extraction script runs, then it processes every PDF in the folder and outputs text for each one.
- [ ] Given a single PDF, when text is extracted, then the output preserves the text content of each page separately (i.e. you can tell which text came from which page).
- [ ] Given a page that contains a table, when it is extracted, then it is routed to pdfplumber and rendered row-by-row with column headers (columns are not jammed together into single lines).
- [ ] Given text with words split across lines by a hyphen (e.g. "decontami-\nnation"), when extraction runs, then the word is rejoined ("decontamination").
- [ ] Given an image-only / scanned page that yields no extractable text, when extraction runs, then that page is flagged (not silently dropped).
- [ ] Given a processed PDF, when the output is checked, then the source filename is logged alongside the extracted text so it can be traced back to the original document.

**Definition of Done:**

- [ ] Extraction is implemented in `src/ingestion/`, runs generically across all sample PDFs, and reads paths from `src/config/`.
- [ ] Matching `pytest` tests in `tests/` assert the acceptance tests above and pass.
- [ ] Extraction has been visually inspected on 3–4 documents for garbled text, merged columns, or missing content.
- [ ] Change is committed on a branch and merged via PR.

**Best Practices:** See `Sprint_1_and_2_Best_Practices.md` §2 Text Extraction (page-by-page, table routing to pdfplumber, hyphenation, image-based text, figures pass through silently).

---

### US-07: Clean extracted text

**Feature:** Document Processing Pipeline | **Sprint:** 1 | **Status:** Backlog

> As a system, I want to clean extracted text so that it is usable for chunking and embeddings.

**Tasks:**

- Strip repeated headers and footers (detected by repetition, not fixed position)
- Strip page-number artifacts
- Strip boilerplate: cover pages, tables of contents, "About WorkSafe" pages, ISBN / copyright lines, standard disclaimer pages
- Fix broken line breaks and standardise spacing
- **Explicitly retain** appendices, tables, warning / callout boxes, glossaries, and legislative references
- Strip by content detection, never by fixed page number

**Acceptance Tests:**

- [ ] Given raw extracted text containing repeated headers and footers, when the cleaning function runs, then those repeated elements are removed and do not appear in the output.
- [ ] Given raw text with broken line breaks mid-sentence and inconsistent spacing, when the cleaning function runs, then the output reads as continuous, properly spaced text.
- [ ] Given raw text with page number artifacts (e.g. standalone "12" or "Page 3 of 10"), when the cleaning function runs, then those artifacts are removed without deleting legitimate numeric content in the document body.
- [ ] Given text containing known boilerplate (e.g. an ISBN line like "978-1-99-..." or a table-of-contents entry), when cleaning runs, then that boilerplate does not appear in the output.
- [ ] Given a document that contains an appendix, table, warning/callout box, glossary, or legislative reference, when cleaning runs, then that content is retained in the output (it is not stripped as boilerplate).
- [ ] Given documents with different amounts of front matter, when cleaning runs, then content is removed by content detection, not by removing a fixed number of leading pages.

**Definition of Done:**

- [ ] Cleaning is implemented in `src/ingestion/`, runs generically across all sample PDFs, and reads settings from `src/config/`.
- [ ] Matching `pytest` tests in `tests/` assert both a "boilerplate removed" case and a "safety content retained" case, and pass.
- [ ] Change is committed on a branch and merged via PR.

**Best Practices:** See `Sprint_1_and_2_Best_Practices.md` §2 Text Extraction (headers/footers, hyphenation) and §3 Boilerplate Stripping (what to strip vs. what NOT to strip; detect by content, not page number).

---

### US-08: Split text into chunks

**Feature:** Document Processing Pipeline | **Sprint:** 1 | **Status:** Backlog

> As a system, I want to split documents into chunks so that they can be used for embeddings later.

**Tasks:**

- Use LangChain `RecursiveCharacterTextSplitter`, configured to prefer heading → paragraph → sentence breaks
- Set chunk size (target 500–1000 tokens; default 1000) with 100–200 tokens overlap (default 200)
- Split at section boundaries and keep the section heading attached to its content
- Keep tables intact as a single chunk (even if oversized); concatenate multi-page tables before chunking
- Do not create chunks from boilerplate; do not carry overlap across a section/topic boundary

**Acceptance Tests:**

- [ ] Given a block of extracted text, when the chunking function runs, then every chunk is between 500-1000 tokens in length (except the final chunk which may be shorter).
- [ ] Given two consecutive chunks within the same section, when compared, then they share an overlapping section (e.g. 100-200 tokens) so that context is not lost at chunk boundaries.
- [ ] Given a short document where total text is under 500 tokens, when the chunking function runs, then it returns a single chunk containing all the text.
- [ ] Given text with section headings, when chunking runs, then chunks break at section boundaries and each chunk retains its section heading; no chunk starts mid-sentence.
- [ ] Given a table (including one spanning multiple pages), when chunking runs, then the table is kept intact as one chunk even if it exceeds the normal size limit.
- [ ] Given two consecutive chunks that fall on either side of a section boundary, when compared, then no overlap is carried across that boundary.

**Definition of Done:**

- [ ] Chunking is implemented in `src/ingestion/` using `RecursiveCharacterTextSplitter`, runs generically across all sample PDFs, and reads chunk-size/overlap from `src/config/`.
- [ ] Matching `pytest` tests in `tests/` assert chunk size bounds, overlap within a section, table-intact behaviour, and no mid-sentence starts, and pass.
- [ ] Output has been spot-checked to confirm no boilerplate or orphaned (heading-less) chunks.
- [ ] Change is committed on a branch and merged via PR.

**Best Practices:** See `Sprint_1_and_2_Best_Practices.md` §4 Chunking (size/overlap, split on structure, tables in chunks, multi-page tables, pitfalls).

---

### US-09: Structure chunk output

**Feature:** Document Processing Pipeline | **Sprint:** 1 | **Status:** Backlog

> As a developer, I want structured chunk output so that each piece of text contains metadata for retrieval.

**Tasks:**

- Format each chunk with its text plus metadata keys: `source_file`, `page_number`, `section_heading`, `chunk_type`
- Set `chunk_type` to one of: `prose`, `table`, `appendix`, `glossary`
- Store chunks in JSON or list format
- Validate output structure

**Acceptance Tests:**

- [ ] Given a processed PDF, when the pipeline outputs chunks, then each chunk carries its text plus the metadata keys `source_file`, `page_number`, `section_heading`, and `chunk_type`, with no empty values.
- [ ] Given chunks from multiple PDFs, when the pipeline runs on the entire document folder, then every chunk's `source_file` field matches the filename of the PDF it came from.
- [ ] Given a chunk that spans two pages, when the pipeline outputs it, then the `page_number` field reflects the starting page (or page range) of that chunk.
- [ ] Given any chunk, when its `section_heading` is checked, then it reflects the heading hierarchy the chunk came from (e.g. "3.0 Licensed asbestos removal > 3.3 ...").
- [ ] Given any chunk, when its `chunk_type` is checked, then it is one of `prose`, `table`, `appendix`, or `glossary`.

**Definition of Done:**

- [ ] Chunk output is implemented in `src/ingestion/` with the four metadata fields, runs generically across all sample PDFs, and reads settings from `src/config/`.
- [ ] Matching `pytest` tests in `tests/` assert every chunk has all four metadata fields populated and that `chunk_type` is within the allowed set, and pass.
- [ ] The field names match the Sprint 2 embeddings/citation contract (this is the source of truth for those names).
- [ ] Change is committed on a branch and merged via PR.

**Best Practices:** See `Sprint_1_and_2_Best_Practices.md` §4 Chunking → "Metadata to Attach to Every Chunk" (`source_file`, `page_number`, `section_heading`, `chunk_type`).

> Note: this story previously specified keys `text` / `source` / `page_number`. The metadata field names now align with the best-practices doc (`source_file`, `page_number`, `section_heading`, `chunk_type`) because Sprint 2 source attribution depends on `section_heading` and `chunk_type`.

---

### US-10: Validate processing pipeline

**Feature:** Document Processing Pipeline | **Sprint:** 1 | **Status:** Backlog

> As a developer, I want to test the full processing pipeline so that I know it works end-to-end before embeddings.

**Tasks:**

- Run the full pipeline (extraction → cleaning → chunking) on sample PDFs
- Assert non-empty output per document
- Assert chunk size bounds and that boilerplate is gone
- Assert required metadata on every chunk
- Assert known table cell values survive extraction

**Acceptance Tests:**

- [ ] Given a set of sample WorkSafe PDFs, when the full pipeline runs (extraction, cleaning, chunking), then every PDF produces non-empty output / at least one chunk and no step throws an error.
- [ ] Given the pipeline output, when chunk sizes are checked, then no chunk exceeds a sane maximum (~2000 tokens) unless it is a table, and none is below a sane minimum (~50 tokens).
- [ ] Given the pipeline output, when metadata is inspected, then every chunk has a valid `source_file` matching the original PDF and a `page_number` within that document's actual page range (plus `section_heading` and `chunk_type`).
- [ ] Given known boilerplate strings (e.g. an ISBN like "978-1-99-"), when the output is checked, then they do not appear in any chunk.
- [ ] Given 2–3 known tables from the documents, when their chunks are checked, then key cell values from those tables appear in the extracted text.

**Definition of Done:**

- [ ] A `pytest` suite in `tests/` runs the full pipeline on sample PDFs and asserts all of the above; it passes.
- [ ] Tests avoid brittle assertions (no checks that a specific sentence lands in a specific chunk) and do not test retrieval quality (that is Sprint 2 / DeepEval).
- [ ] A one-command runner (e.g. in `scripts/`) can execute the full pipeline end-to-end.
- [ ] Change is committed on a branch and merged via PR.

**Best Practices:** See `Sprint_1_and_2_Best_Practices.md` §5 Testing the Pipeline (what to test vs. what NOT to test).

## Sprint 2

<!-- Add user stories below. -->

