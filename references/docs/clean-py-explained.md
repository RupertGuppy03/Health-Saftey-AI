# `clean.py` explained (for the team)

**File:** `src/ingestion/clean.py`
**Status:** Spike / proposal — the switch from PyMuPDF/pdfplumber to Unstructured.io
is **paused pending team sign-off**. This does not change any user story yet.

Think of `clean.py` as a **sorting-and-tidying machine**: raw messy JSON from
Unstructured goes in one end, and a clean, labelled list of text blocks comes out
the other — ready for the chunking step.

---

## Where it sits in the pipeline

```
Raw PDF → Unstructured.io → raw JSON → clean.py → CLEANED JSON
        → chunking (Luca) → embedding → ChromaDB
```

- **Input:** the cached Unstructured JSON (`data/processed/<doc>/*.pdf.json`).
- **Output:** `..._CLEANED.json` (the real data) + `..._CLEANED-preview.txt` (readable).
- Makes **no API call** and adds **no new dependency** — pure Python standard library
  on top of the already-saved JSON, so it runs the same way every time (reproducible).

---

## The setup at the top (the "rulebooks")

Before any functions, the file defines lists it checks against:

| Name | What it is |
|---|---|
| `KEEP_TYPES` | Block types worth keeping: paragraphs, headings, bullets, tables. Everything else (headers, footers, page numbers, images) is dropped. |
| `BOILERPLATE_PHRASES` + `ISBN_RE` | Words/patterns that mark junk (ISBN, "Creative Commons", disclaimers). |
| `TOC_HEADINGS` | Just the word `"contents"`, used to find where the table of contents starts. |
| `GLYPH_ARTIFACTS` | A small fix-list for broken words like `di(erent → different`. |

---

## The functions, one by one

**`normalise_text(text)` — the spell-fixer**
Cleans a piece of text: fixes squashed ligatures (`ﬁ → fi`), swaps known broken
words, and collapses extra spaces/line breaks into single spaces.

**`find_suspicious_tokens(text)` — the quality inspector**
Scans for words that *still* look broken after fixing (a bracket or digit wedged
inside letters) and reports them, so nothing bad slips through silently.

**`_TableParser` + `html_table_to_markdown(html)` — the table rebuilder**
Unstructured gives tables as HTML. This reads the HTML, pulls out the rows and
cells, and rewrites the table as clean Markdown (`| column | column |`) so the rows
and columns survive. *(This is the big win over pdfplumber, which lost columns.)*

**`is_boilerplate(text)` — the junk detector**
Returns yes/no: does this text look like an ISBN line, disclaimer, or copyright
notice? If yes, it gets dropped.

**`classify_chunk_type(type, heading)` — the labeller**
Decides what kind of content a block is: `glossary`, `appendix`, `table`, or
`prose`. This is one of the four metadata labels the next step needs.

**`_looks_like_body_paragraph(type, text)` — a small helper**
Answers "is this a real paragraph?" (long, starts with a letter, ends in a full
stop). Used to know when the table of contents has ended and real content begins.

**`clean_elements(elements, source_file)` — the main engine**
The heart of the file. It walks through every block in the JSON and, for each one:
1. Drops it if it is not a `KEEP_TYPE`.
2. Cleans the text (or rebuilds it as Markdown if it is a table).
3. Skips the table-of-contents block.
4. Drops boilerplate.
5. Remembers the current section heading.
6. Saves a tidy **record** with its text plus four metadata fields.
It also counts what it dropped and returns a short **report**.

**`_find_cached_json()` — the file finder**
Locates the raw Unstructured JSON in the data folder.

**`main()` — the conductor**
Ties it all together when you run the script: find the JSON → run `clean_elements`
→ save the two output files → print the summary (kept/dropped counts).

---

## The output: what one "record" looks like

Each cleaned block becomes a record with the metadata the chunking step needs
(the locked US-09 schema):

```json
{
  "text": "| TERM | LEGAL DEFINITION ... |\n| --- | --- |\n| Contractor | A PCBU who ... |",
  "source_file": "PCBUs-Working-Together-GPG.pdf",
  "page_number": 33,
  "element_type": "Table",
  "section_heading": "Appendix 4: Glossary",
  "chunk_type": "glossary"
}
```

---

## One-sentence summary

> `main` loads the raw JSON and hands it to `clean_elements`, which loops through
> every block — dropping junk (`is_boilerplate`, type filter), fixing text
> (`normalise_text`), rebuilding tables (`html_table_to_markdown`), and labelling
> each piece (`classify_chunk_type`) — then saves a clean, labelled list ready for
> chunking.

---

## How to run it

```bash
.venv/bin/python -m src.ingestion.clean
```

Writes `..._CLEANED.json` and `..._CLEANED-preview.txt` into the document's folder
under `data/processed/`. Tests live in `tests/ingestion/test_clean.py`.

---

## Known limitations (be upfront with the team)

- **`section_heading` is best-effort.** Unstructured over-tags short lines as
  headings, so this field is sometimes a sentence fragment. The proper heading
  hierarchy is finalised during **chunking (US-09, Luca's step)**.
- **Complex tables (rowspan / multi-line cells) can have minor text-order
  scrambling** — e.g. Table 1 "Common shared duties". The content is all present
  and columns are preserved, but wording isn't always verbatim. Simple tables (the
  glossary) come out perfect.
- **Multi-page tables** (e.g. the glossary spans pages 33–34) arrive as two table
  records — rejoining them is a **chunking-step** job.
- The boilerplate rules are tuned to the **WorkSafe** style; proven on PCBUs, not
  yet validated across the other 19 documents.
