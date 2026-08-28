# US-06 Manual Validation Checklist

Purpose

This file is a ready-to-copy checklist for testers to manually verify that the retrieval→LLM pipeline (US-06) returns grounded answers with correct source attributions. Run the checks below against the local API or by calling the `answer_question` helper.

Prerequisites

- Project dependencies installed (use the repo's `requirements.txt`).
- A Python 3.10+ executable available on PATH as `python3`.
- If you want to run the live LLM (not required for the tests below), create a `.env` file with either `OPEN_AI_API_KEY` or `OPENAI_API_KEY`.
- (Optional but required for real end-to-end checks) Populate the ChromaDB vectorstore by running the ingestion pipeline so the collection contains the project PDFs.

How to run

1. Start the API (development):

    ./scripts/run_api.sh

   This launches the FastAPI app on http://127.0.0.1:8000 by default.

2. Or run queries directly from Python (call `src.answer.answer_question` in a Python REPL or script).

Sample curl

```bash
curl -sS -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What edge protection do I need on a roof?"}'
```

Five validation queries

1. "What edge protection do I need on a roof?"
   - Expectation: Answer grounded in construction guidance, cites `working-on-roofs.pdf` or similar.

2. "How deep can a trench be before special controls are needed?"
   - Expectation: Retrieval of excavation guidance and a citation to the relevant section/page.

3. "Which personal protective equipment is recommended for welding in confined spaces?"
   - Expectation: Practical PPE guidance from a relevant document and an appropriate citation.

4. "When must guardrails be installed on a work platform?"
   - Expectation: Prescriptive guidance that cites the source document and section.

5. "Does the corpus give guidance on ladder inspection frequency and how should I record it?"
   - Expectation: Advice plus citation on ladder inspection/record-keeping from a relevant doc.

Manual checklist (run for each query)

1. Run the query via the API or `answer_question`.

2. Confirm status in response:
   - `status == "ok"` for covered topics.
   - If `status == "no_results"`, confirm the message clearly states no relevant information was found.

3. Inspect the answer text:
   - It should use language grounded in the retrieved context (no invented facts).
   - If the answer is vague or plainly not supported by the corpus, flag it.

4. Inspect the `sources` array in the response:
   - Each source entry should include at least: `chunk_id`, `source_file`, `page_number`, `section_heading`.
   - Record the returned `chunk_id` and metadata for later verification.

5. Verify citations against the original PDF(s):
   - Open the cited source file at the cited page number and section heading.
   - Confirm the content in the PDF / chunk supports the answer's claims.
   - Confirm the `section_heading` and `page_number` returned by the pipeline match the PDF.

6. Metadata parity check (against ChromaDB):
   - Use the `scripts/check_chroma_collection.py` script or a small Python snippet to open the collection and retrieve the stored metadata for the returned `chunk_id`.
   - Confirm the metadata fields (`source_file`, `page_number`, `section_heading`) match exactly what the API returned.

7. Error handling check (LLM failure):
   - Temporarily alter the LLM dependency to a failing stub, or set invalid credentials and run the same query.
   - Expected: API returns `status == "error"` with a descriptive `error` field and HTTP 500 for the /ask endpoint.
   - Confirm the system does not crash and that the error is user-friendly.

8. Off-topic / no-hit check:
   - Ask an obviously off-topic question (e.g., "What is the capital of France?").
   - Expected: `status == "no_results"` and a clear message.

Pass / Fail criteria (per query)

- PASS if:
  - `status == "ok"`.
  - `answer` text is grounded and traceable to the cited sources.
  - `sources` array contains metadata and `chunk_id`.
  - The cited PDF page and section contain the supporting text.
  - Metadata retrieved from the ChromaDB collection matches the API-returned metadata.

- FAIL if:
  - `status == "error"` without a helpful message.
  - `answer` contains claims not supported by the cited sources.
  - `sources` metadata does not match what's stored in ChromaDB.
  - The system crashes or raises an unhandled exception.

Recording results

- For each query, record:
  - Query text
  - Response `status`
  - Short extract of the `answer` (1–2 lines)
  - Returned `sources` metadata (copy the JSON)
  - PDF pages/sections verified and any mismatches found

- Save these per-query records to accompany your PR review and H&S lead review.

Notes

- Tests provided in `tests/` (unit and integration) cover structural behavior (happy path / no-results / LLM error). The manual checks above validate that the textual grounding and source attributions are correct against the original PDFs — this must be done manually as part of Definition of Done.

- If a returned `section_heading` looks wrong but the page contains the supporting text, consider whether the chunking or heading-detection logic needs refinement (Sprint 1 locked behaviour: headings detection, hybrid extraction, chunk overlap rules). Report any systematic mismatches as issues.

- If you want, after finishing the 5 checks, reply here and I will mark `rag-chain-validation` as `done` in the session TODOs.
