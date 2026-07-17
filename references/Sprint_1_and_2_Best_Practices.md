# Sprint 1 & 2: Best Practices, Pitfalls, and Things to Avoid

Health and Safety AI — RAG Document Processing and System Build

Prepared by Rupert Guppy — July 2026

## Overview

This document covers the pitfalls, best practices, and things to avoid when building the document processing pipeline (Sprint 1) and the RAG system (Sprint 2). It is written for the team to reference during development. It does not contain code — it tells you what to do, what not to do, and why.

Our source documents are 20 WorkSafe NZ good practice guides for the construction industry, ranging from roughly 30 to 190+ pages. They contain prose, tables, headings, figures, appendices, and boilerplate. The processing pipeline needs to turn these into clean, structured text chunks that our RAG system can retrieve from accurately.

## Key Principle: Don't Manually Trim Documents

Do not open PDFs and manually remove pages, sections, appendices, or figures. This does not scale, breaks reproducibility, and risks removing content that is actually valuable for retrieval (especially appendices, which contain checklists, hazard tables, and risk matrices).

Instead, handle all cleaning programmatically in the processing pipeline. If a specific section is genuinely irrelevant, exclude it by detecting its heading in code, not by editing the PDF. The only manual decision is whether to include or exclude a document entirely from the corpus.

---

# Sprint 1: Document Processing Pipeline

## 1. Document Sourcing

This is the simplest part of Sprint 1. Download the 20 construction documents from the WorkSafe publications hub. Place them in the raw data folder in the repo. No editing, no trimming.

### Pitfalls

- Do not rename PDFs to something generic. Keep the original filenames or use a consistent naming convention that includes the document title. The filename becomes metadata that helps with source attribution later.
- Do not convert PDFs to another format before processing. Work with the original PDFs directly.
- Do not start filtering or reading through documents at this stage. The processing pipeline handles that.

## 2. Text Extraction

We are using a hybrid extraction approach: PyMuPDF for regular prose text, and pdfplumber for pages that contain tables. PyMuPDF is faster and produces cleaner prose output. pdfplumber has built-in table detection that preserves row and column structure.

### Best Practices

- Extract text page by page, not the entire document at once. This lets you attach page numbers to each chunk as metadata.
- When a page contains a table, switch to pdfplumber's `extract_tables()` method for that page. Convert the table into a readable text format (row-by-row, with column headers repeated or labelled per row) rather than leaving it as raw column-aligned text.
- Preserve heading hierarchy. PyMuPDF can detect font sizes. Use this to identify section headings (e.g. "3.3 Changes to friability and classification of removal work") and keep them attached to the content that follows them.
- Run extraction on every document and visually inspect the output of at least 3-4 documents before moving on to chunking. Look for garbled text, merged columns, missing content, or encoding issues.

### Pitfalls

- **Tables will break with PyMuPDF alone.** PyMuPDF extracts text line by line based on position. For multi-column tables, this means columns get merged into single lines with no separation. If you see table content where column values are jammed together, that page needs pdfplumber instead.
- **Watch for image-based text.** Some of the WorkSafe PDFs have text rendered as images (especially older documents or scanned pages). PyMuPDF will return empty strings for these pages. If you get blank pages where content should exist, flag it — you may need OCR (not in scope for v1, but worth knowing about).
- **Repeating headers/footers pollute chunks.** Headers and footers repeat on every page (e.g. "WorkSafe New Zealand" at the top, page numbers at the bottom). If you don't strip these, they end up in your chunks and dilute retrieval quality. PyMuPDF lets you check if the same text appears at the same coordinates on multiple pages — that's your footer/header.
- **Figures are not a problem.** Figures in these documents (diagrams, photos of equipment) will not extract as text. This is fine — figures don't contain text content that a RAG system can use. Do not try to extract or describe images. Just let them pass through silently.
- **Hyphenated words across lines.** Hyphenated line breaks (where a word is split across two lines with a hyphen) need to be rejoined. Otherwise "decontami-" and "nation" become two separate tokens and won't match queries properly.

### Things to Avoid

- Do not try to extract every type of content perfectly in Sprint 1. Get prose and tables working well. Edge cases like sidebar callout boxes or coloured warning panels can be improved later.
- Do not spend time writing custom logic for every document individually. The pipeline should work generically across all 20 documents. If one document has a unique layout problem, note it and move on.

## 3. Boilerplate Stripping

Boilerplate is content that appears in the documents but has no value for answering health and safety questions. Stripping it reduces noise in your vector store and improves retrieval accuracy.

### What to Strip

- Cover pages (title, ISBN, copyright notice, publication date).
- Tables of contents — these are navigation aids, not content. If a user asks about asbestos enclosures, you want the actual section, not the ToC entry that says "9.0 Asbestos removal enclosures ... 43".
- "About WorkSafe New Zealand" boilerplate pages that appear at the start or end of most documents.
- Repeating headers and footers on every page.
- ISBN and copyright lines (e.g. "978-1-99-105749-5 (online)").
- Disclaimer pages that are standard legal text, not health and safety guidance.

### What NOT to Strip

- **Appendices** — these often contain the most retrievable content: checklists, hazard tables, risk matrices, worked examples, decision flowcharts. The asbestos removal guide has 6 appendices spanning 30 pages of highly practical reference material.
- **Tables** — these are core content (PPE requirements, licence categories, removal scenarios). See the extraction section for how to handle them.
- **Warning/callout boxes** — these contain critical safety information like "Any removal work that requires controls associated with friable asbestos removal should be treated as Class A asbestos removal work." These are some of the most useful chunks for retrieval.
- **Glossaries** — these help the model understand domain-specific terminology when it appears in retrieved context.
- **Legislative references** — cross-references to legislation (e.g. references to the HSWA 2015 or the Asbestos Regulations 2016) provide legal grounding that the system should be able to surface.

### Pitfalls

- Do not strip content just because it looks like boilerplate at a glance. Some documents have important safety notices formatted to look like standard disclaimers. Check the actual content before writing a removal rule.
- Do not strip based on page number (e.g. "remove the first 5 pages"). Different documents have different amounts of front matter. Strip based on content detection (font size patterns, repeated text, keyword matching for known boilerplate phrases).

## 4. Chunking

Chunking is the most important part of the processing pipeline. It determines what the retrieval system can find and how useful the retrieved context is to the LLM. Bad chunking leads to bad answers, regardless of how good the rest of the system is.

### Chunk Size and Overlap

- Target 500-1000 tokens per chunk. Start with 1000 tokens as a default.
- Use 100-200 tokens of overlap between consecutive chunks. Start with 200 tokens.
- Too small (under 300 tokens): chunks lose context. A chunk that says "wear P2 respirators" without mentioning it relates to asbestos removal will match PPE queries from any industry and return irrelevant results.
- Too large (over 1500 tokens): chunks become unfocused. A chunk covering 10 different hazard types will weakly match lots of queries but strongly match none.
- These are starting values. Tune them in Sprint 2 based on actual retrieval results.

### Split on Structure, Not Just Character Count

- **Use RecursiveCharacterTextSplitter.** LangChain's `RecursiveCharacterTextSplitter` tries to break on headings, then paragraphs, then sentences, then characters (in that order). Configure the separators properly so it prefers structural breaks.
- **Split at section boundaries.** The ideal chunk boundary is a section heading. Section 9.5 "Enclosure design and main features" should be one or more chunks that each contain the section title, not a chunk that starts mid-sentence from the previous section.
- **Use headings as split markers.** If your extraction step preserves heading information (font size detection from PyMuPDF), you can insert markers like `\n## 9.5 Enclosure design and main features\n` before the section content. The splitter will then prefer to break at these markers.

### Handling Tables in Chunks

- A table should be kept as one chunk, even if it exceeds the normal chunk size limit. A 1,200 token table that stays intact is far more useful than two 600 token fragments where neither makes sense on its own.
- When you convert a table to text during extraction, prepend the table's context heading (e.g. "Table 3: Examples of when method of removal may change asbestos friability") so the chunk is self-contained.
- For tables that span multiple pages (like the friability table in the asbestos guide), concatenate the content from both pages before creating the chunk. Detect continuation by checking if the next page starts with the same column headers or continues rows without a new heading.

### Handling Multi-Page Tables

Several of the WorkSafe documents have tables that span 2 or more pages. The asbestos removal guide has this with the friability classification table (section 3.3). If you chunk pages independently, the table gets split and both halves become useless for retrieval.

- During extraction, detect when a table continues onto the next page. Signs: the next page starts with table rows but no table title, or the same column headers repeat at the top of the next page.
- Concatenate the rows from all pages of the table into one block of text before chunking.
- If the combined table exceeds your chunk size limit, it is still better to keep it as one oversized chunk than to split it arbitrarily.

### Metadata to Attach to Every Chunk

- `source_file`: the PDF filename (e.g. "asbestos_removal.pdf").
- `page_number`: the page(s) the chunk came from.
- `section_heading`: the heading hierarchy (e.g. "3.0 Licensed asbestos removal > 3.3 Changes to friability and classification of removal work").
- `chunk_type`: whether this chunk is "prose", "table", "appendix", or "glossary". This can help with retrieval filtering later.

This metadata is used in Sprint 2 for source attribution ("Print source documents used to verify retrieval") and can be used for filtered retrieval in later sprints.

### Pitfalls

- **Mid-sentence splits.** Do not split chunks in the middle of a sentence. `RecursiveCharacterTextSplitter` handles this if configured correctly, but verify by inspecting the output.
- **Orphaned chunks.** Do not strip the section heading from a chunk. If a chunk contains content from section 9.5 but doesn't include the heading "Enclosure design and main features", the retrieval system has no structural context for what the chunk is about.
- **Overlap across topic boundaries.** If two consecutive chunks are about completely different topics (e.g. the end of section 9 and the start of section 10), the overlap between them creates a Frankenstein chunk that confuses retrieval. When you detect a section boundary, start a new chunk cleanly without overlap from the previous section.
- **Boilerplate chunks.** Do not create chunks from table-of-contents pages, cover pages, or other boilerplate. These will match many queries superficially (they contain lots of keywords) but provide no useful answers. Strip boilerplate before chunking, not after.

## 5. Testing the Pipeline (pytest)

Sprint 1 includes writing pytest tests for the processing pipeline. Focus on tests that catch real problems, not tests for the sake of coverage.

### What to Test

- Extraction produces non-empty output for every document (catches image-based PDFs or corrupted files).
- Boilerplate stripping removes known boilerplate (e.g. assert that "978-1-99-" does not appear in any chunk).
- No chunk exceeds a sensible maximum size (e.g. 2000 tokens) unless it is a table.
- No chunk is below a sensible minimum size (e.g. 50 tokens) — very small chunks are usually extraction artifacts.
- Every chunk has the required metadata fields (`source_file`, `page_number`, `section_heading`).
- Table extraction produces readable output — pick 2-3 known tables from the documents and assert that key cell values appear in the extracted text.

### What NOT to Test

- Do not test whether specific sentences from specific pages appear in specific chunks. That makes your tests brittle and they break every time you adjust chunk size or overlap.
- Do not write tests for retrieval quality. That is Sprint 2 work (DeepEval).

---

# Sprint 2: RAG System

## 6. Embeddings and ChromaDB

Once the processing pipeline produces clean chunks with metadata, Sprint 2 turns them into embeddings and stores them in ChromaDB for retrieval.

### Best Practices

- Use OpenAI's text-embedding model for consistency with the rest of the stack. Embed each chunk as a single string.
- Store all metadata fields alongside the embedding in ChromaDB. You will need `source_file` and `section_heading` at minimum for source attribution in the UI.
- Persist ChromaDB to disk (the `vectorstore/` folder in the repo). This avoids re-embedding every time you restart the application, which saves time and API cost.
- Run the embedding + storage as a single script (`ingest_all.py`). Any team member should be able to run one command to go from raw PDFs to a populated vector store.

### Pitfalls

- **Duplicate embeddings.** Embedding the same document twice creates duplicate chunks in ChromaDB. Use a unique ID per chunk (e.g. filename + page number + chunk index) so re-running the ingestion script overwrites existing entries rather than duplicating them.
- **Stale embeddings after pipeline changes.** If you change your chunking strategy (different size, different overlap, different boilerplate rules), you need to re-embed everything. Don't assume old embeddings are still valid after pipeline changes.
- **Use named collections.** ChromaDB has a default collection. Create a named collection (e.g. "hs_construction_v1") so you can version your vector store if needed.

## 7. RAG Query Pipeline

The RAG pipeline connects ChromaDB retrieval to GPT-4o via LangChain. A user query gets embedded, matched against chunks, and the top chunks get sent to the LLM as context alongside the query.

### Best Practices

- Retrieve 4-6 chunks per query as a starting point. Too few and you miss relevant context. Too many and you flood the LLM's context window with noise, increasing cost and reducing answer quality.
- Return the metadata (source file, page number, section heading) alongside the retrieved chunks. You need this for source attribution and for debugging retrieval quality during testing.
- Build a terminal test script first (before the Streamlit UI). This lets you iterate on retrieval quality and prompt engineering without dealing with UI concerns.

### Pitfalls

- **Retrieval returning scattered, unrelated chunks.** If retrieval returns chunks from 4 different documents about 4 different topics, the LLM will try to synthesise them into one answer, which produces vague, blended responses. This usually means your chunks are too large or your embedding quality is poor. Check your Sprint 1 pipeline first before blaming the LLM.
- **LLM ignoring retrieved context.** The LLM will sometimes answer from its own training data instead of the retrieved context, especially if the retrieved chunks don't fully answer the question. Your system prompt needs to explicitly instruct the model to only answer from provided context and to say "I don't have enough information to answer that" when the context is insufficient.
- **Wrong source attribution.** If the LLM gives a correct answer but cites the wrong source document, the problem is usually in your metadata — either the wrong metadata was attached during chunking, or you're not passing metadata through correctly in the LangChain chain.

## 8. System Prompt and Guardrails

The system prompt defines how the model behaves. For a health and safety application, this is critical — wrong answers can have real consequences.

### What the System Prompt Must Do

- Instruct the model to only answer from the provided context (retrieved chunks). It must not make up health and safety advice from its own training data.
- Include a disclaimer that this is general guidance, not legal or professional health and safety advice. This aligns with your project scope.
- Tell the model to cite which source document and section its answer came from.
- Instruct the model to say it cannot answer if the retrieved context does not contain relevant information, rather than guessing.
- Specify that responses should be in plain, clear language suitable for SME business owners who are not health and safety experts.

### Pitfalls

- **Too vague.** A vague system prompt like "You are a helpful health and safety assistant" gives the model too much freedom. It will answer questions outside your document scope using its training data. Be specific about boundaries.
- **Disclaimer fatigue.** Do not put the disclaimer in the system prompt in a way that makes the model repeat it in every response. Users will ignore it. Put it once in the UI instead, and have the system prompt focus on behaviour.
- **Test edge cases.** Test the prompt with adversarial queries: "What is the capital of France?" (should refuse — not H&S), "Should I sue my employer?" (should refuse — legal advice), "What PPE do I need for painting?" (should answer only if painting guidance exists in the documents, otherwise say it doesn't have information on that topic).

## 9. Testing and Retrieval Quality

Sprint 2 includes building a terminal test script and tracking early metrics like latency and answer alignment.

### Best Practices

- Write 10-15 golden Q&A pairs that cover a range of topics from your documents. Each pair has a question a real user would ask, the expected answer, and which document(s) the answer should come from. These become your DeepEval test cases.
- Test retrieval separately from generation. Before you check whether the LLM gives a good answer, check whether the right chunks are being retrieved. If retrieval is wrong, no amount of prompt engineering will fix the answer.
- Track response latency from the start. Wrap the API call with a timer. Your target is under 5 seconds. If you're consistently over that, the bottleneck is usually the number of retrieved chunks being too high or the system prompt being too long.

### Pitfalls

- **Subjective evaluation.** Do not evaluate answers by reading them and deciding they "sound right". Use your golden Q&A pairs and the DeepEval metrics. Human judgment is inconsistent and doesn't scale.
- **Only testing easy queries.** Do not skip testing retrieval on questions that span multiple documents (e.g. "What PPE requirements apply to both asbestos removal and scaffolding work?"). These cross-document queries are where RAG systems struggle most and where you'll find real problems.
- **Wrong debugging order.** If answers are bad, debug in this order: (1) Are the right chunks being retrieved? (2) Are the chunks clean and readable? (3) Is the system prompt clear enough? (4) Is the chunk size appropriate? Most problems are at step 1 or 2, not at the LLM level.

---

## Quick Reference: Common Problems and Where to Fix Them

**If the system gives vague or blended answers:** check chunk size (probably too large) and retrieval count (probably returning too many unrelated chunks). Fix in the processing pipeline, not the prompt.

**If the system gives confident but wrong answers:** check whether the LLM is answering from training data instead of context. Tighten the system prompt. Check if the retrieved chunks actually contain the right information.

**If the system says it can't answer when it should be able to:** check whether the relevant content survived extraction and chunking. Inspect the chunks for that topic. The information might have been stripped as boilerplate or lost in a badly extracted table.

**If source citations are wrong:** check the metadata attached during chunking. The metadata is probably misaligned (wrong page number, wrong section heading, or wrong source file).

**If responses are too slow:** check how many chunks you're retrieving (reduce from 6 to 4), how long your system prompt is (trim it), and whether ChromaDB persistence is working (re-embedding on every query is very slow).

**If tables come back as garbled text:** the extraction step is using PyMuPDF for a page that contains a table. Switch that page to pdfplumber extraction.