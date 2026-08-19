# Sprint 2 — Embeddings & core RAG pipeline

Planning docs and user stories for this sprint. Goal: embeddings, ChromaDB
setup, the core LangChain RAG pipeline, system prompt, terminal testing, and a
latency timer. See [`../Project_User_Stories.md`](../Project_User_Stories.md).


# Sprint 2 User Stories — RAG System Build

**Sprint goal:** Build the core RAG pipeline so the system can answer questions grounded in WorkSafe NZ guidance.
**Duration:** 3 weeks
**Stories:** 11 (10 Must, 1 Should)

---

## Shared Definition of Done

Applies to every story. Story-specific DoD items are listed under each card in addition to these.

- All acceptance tests pass and are demonstrated to the assigned tester
- Code reviewed by at least one other team member before the card moves to Done
- Code merged to `main` with no broken imports on a clean clone
- Any new environment variable or config value documented in the README
- No API keys, endpoints or secrets committed to the repo
- Burndown chart updated when the card moves to Done

---

## 1. Set Up the ChromaDB Vector Store

**MoSCoW:** Must | **Est:** 1–2 days

As a developer, I want a named, persisted ChromaDB collection so that embeddings survive application restarts and the vector store can be versioned.

**Tasks**
- Install and configure ChromaDB as a persistent client
- Create a named collection (e.g. `hs_construction_v1`)
- Persist the store to the `vectorstore/` folder in the repo
- Add `vectorstore/` handling to `.gitignore` and document the decision
- Write a small script or function to confirm the collection can be opened and counted

**Acceptance Tests**
- Given ChromaDB is configured, when the store is initialised, then a named collection is created rather than the default collection.
- Given the vector store has been written to, when the application is restarted, then the existing collection is loaded from `vectorstore/` without re-embedding.
- Given the collection exists, when the collection count is queried, then the number of stored items is returned.

**Definition of Done**
- The collection name is defined in one place in config, not hardcoded across multiple files
- A team member can clone the repo and open the persisted collection without running ingestion first

---

## 2. Embed Cleaned Chunks and Store Them with Metadata

**MoSCoW:** Must | **Est:** 2–3 days

As a developer, I want each cleaned chunk embedded and stored in ChromaDB with its metadata so that retrieved chunks can be traced back to their source document.

**Tasks**
- Load the cleaned chunks produced by the Sprint 1 chunking script
- Embed each chunk as a single string using the OpenAI text-embedding model
- Store `source_file`, `page_number` and `section_heading` alongside every embedding
- Confirm whether the Sprint 1 output includes `chunk_type` and store it if present
- Spot check a sample of stored records to confirm metadata alignment

**Acceptance Tests**
- Given clean document chunks, when the embedding script runs, then each chunk is converted into an embedding and stored in the named collection.
- Given a stored chunk is retrieved by ID, when its metadata is inspected, then `source_file`, `page_number` and `section_heading` are all present and non-empty.
- Given a sample of 10 stored chunks, when the stored text is compared against the source document, then the metadata points to the correct document and page.

**Definition of Done**
- No chunk is stored with a missing or empty metadata field
- The metadata field names match the names used by the Sprint 1 chunking script exactly

---

## 3. Make Ingestion Idempotent with Unique Chunk IDs

**MoSCoW:** Must | **Est:** 2 days

As a developer, I want re-running ingestion to overwrite existing chunks instead of duplicating them so that the vector store stays clean during development.

**Tasks**
- Define a deterministic unique ID per chunk (e.g. filename + page number + chunk index)
- Use the ID on insert so repeated runs upsert rather than append
- Add a way to clear or rebuild the collection when the chunking or cleaning logic changes
- Record the pipeline version or config used for the current embeddings

**Acceptance Tests**
- Given the ingestion script has already run, when it is run again over the same documents, then the collection count does not increase.
- Given the same chunk is ingested twice, when the collection is queried by that chunk ID, then exactly one record is returned.
- Given the chunking or cleaning configuration has changed, when ingestion is re-run, then the affected documents are re-embedded rather than left stale.

**Definition of Done**
- Running ingestion twice in a row is demonstrated live to the tester with the collection count shown before and after
- The rebuild path is documented so a team member knows when they must re-embed

---

## 4. Create a One-Command Ingestion Script

**MoSCoW:** Must | **Est:** 2 days

As a team member, I want a single notebook so that anyone can go from cleaned chunks to a populated vector store one document at a time.

**Tasks**
- Wire chunk loading, embedding and ChromaDB storage into one entry point
- Add progress output showing which document is being processed
- Print a summary at the end: documents processed, chunks stored, failures
- Handle and report a failed document without aborting the whole run

**Acceptance Tests**
- Given a populated cleaned-chunks folder, when notebook is run, then the vector store is populated without any further manual steps.
- Given the script completes, when the summary is printed, then the number of documents processed and chunks stored is shown.
- Given one document fails to process, when the script runs, then the failure is reported and the remaining documents still complete.

**Definition of Done**
- A team member other than the developer runs the script successfully from a clean clone
- The final chunk count in ChromaDB matches the count reported by the script

---

## 5. Retrieve Relevant Chunks for a User Query

**MoSCoW:** Must | **Est:** 2–3 days

As a user, I want my question matched against the document chunks so that the most relevant guidance is found before an answer is generated./model

**Tasks**
- Embed the incoming user query using the same embedding model as ingestion
- Run a similarity search against the named ChromaDB collection
- Return the top 4–6 chunks as the initial retrieval setting
- Return chunk metadata alongside the chunk text
- Make the retrieval count configurable in one place

**Acceptance Tests**
- Given a user question, when the retrieval function receives the query, then the query is converted into an embedding using the same model used at ingestion.
- Given an embedded query, when retrieval runs, then between 4 and 6 chunks are returned.
- Given retrieval has completed, when the results are inspected, then each returned chunk includes its `source_file`, `page_number` and `section_heading`.
- Given a question about a topic clearly covered by one document, when retrieval runs, then at least one returned chunk comes from that document.

**Definition of Done**
- The retrieval count is a single configurable value, not repeated across files
- Retrieval is verified on at least 5 manual queries covering different documents

---

## 6. Connect Retrieval to GPT-4o via LangChain

**MoSCoW:** Must | **Est:** 2–3 days

As a user, I want retrieved chunks passed to GPT-4o so that I get a written answer grounded in the source documents.

**Tasks**
- Build the LangChain chain connecting the retriever to GPT-4o
- Pass retrieved chunk text and metadata into the prompt context
- Return the generated answer together with the sources used
- Handle API errors and empty retrieval results without crashing

**Acceptance Tests**
- Given retrieved chunks, when the chain runs, then GPT-4o returns an answer that uses the retrieved content.
- Given an answer has been generated, when the response is inspected, then the source documents and sections used are returned alongside the answer.
- Given retrieval returns no chunks, when the chain runs, then the system reports that no relevant information was found instead of generating an answer.
- Given the OpenAI API returns an error, when the chain runs, then the error is caught and reported rather than crashing the script.

**Definition of Done**
- Source attribution is manually verified against the source PDFs on at least 5 queries
- Metadata passed through the chain matches the metadata stored in ChromaDB

---

## 7. Write the System Prompt and Guardrails

**MoSCoW:** Must | **Est:** 2 days

As a user, I want the assistant restricted to the retrieved documents so that it does not invent health and safety advice.

**Tasks**
- Write a system prompt instructing the model to answer only from provided context
- Instruct the model to state when the context does not contain enough information
- Instruct the model to handle questions outside the health and safety document scope
- Instruct the model to cite the source document and section
- Specify plain language suitable for SME business owners who are not H&S experts
- Keep the prompt focused on behaviour, not on repeating a disclaimer in every answer
- Store the prompt in a version-controlled file, not inline in the pipeline code

**Acceptance Tests**
- Given relevant retrieved context, when the user asks a health and safety question, then the answer uses only the provided context.
- Given the retrieved context does not contain enough information, when the user asks a question, then the assistant states it does not have enough information rather than guessing.
- Given an answer is generated, when the response is read, then it cites the source document and section it came from.
- Given any successful answer, when the response is read, then the general guidance disclaimer is not repeated inside the answer body.

**Definition of Done**
- The system prompt lives in its own file and changes to it are visible in version control
- Reviewed by the H&S lead for language suitable for a non-expert audience

---

## 8. Test the System Prompt Against Edge and Adversarial Cases

**MoSCoW:** Must | **Est:** 2 days

As a team, we want the guardrails tested against out-of-scope and adversarial questions so that we know the boundaries hold before the UI is built.

**Tasks**
- Write a set of adversarial and edge case test questions covering: off-topic, legal advice, and in-scope topics not present in the corpus
- Run each question through the pipeline and record the actual behaviour
- Record which cases the prompt fails and iterate on the prompt
- Document the final results in the repo

**Acceptance Tests**
- Given an off-topic question such as "What is the capital of France?", when the assistant receives it, then it will anser it by prompting the user to ask and actual H&S question to keep anwsers in the  scope.
- Given a question requiring legal advice such as "Should I sue my employer?", when the assistant receives it, then it does not provide legal advice.
- Given a health and safety question on a topic not covered by the corpus, when the assistant receives it, then it states it does not have information on that topic rather than answering from training data.
- Given the full edge case set is run, when results are recorded, then every case has a recorded pass or fail outcome.

**Definition of Done**
- All edge cases pass, or any remaining failure is logged in the issue register with an owner
- The test question set is committed to the repo so it can be re-run after prompt changes

---

## 9. Build the Terminal Test Script

**MoSCoW:** Must | **Est:** 2 days

As a developer, I want a terminal script for asking questions so that I can iterate on retrieval and prompt quality before any UI work begins.

**Tasks**
- Accept a question from the terminal and run it through the full pipeline
- Print the generated answer
- Print the retrieved chunks with their source file, page number and section heading
- Wrap the pipeline call in a timer and print response latency
- Document how to run it in the README

**Acceptance Tests**
- Given a question typed into the terminal, when the script runs, then an answer is printed along with the sources used.
- Given a query has completed, when the output is displayed, then the retrieved chunks and their metadata are printed for inspection.
- Given any query, when the pipeline completes, then response latency is printed in seconds.

**Definition of Done**
- Another team member runs the script and gets an answer without help from the developer
- No Streamlit or UI code is required to run it

---

## 10. Create the Golden Q&A Test Set

**MoSCoW:** Must | **Est:** 2 days

As a team, we want 10–15 golden Q&A pairs so that RAG quality is measured against a fixed benchmark instead of subjective judgement. Possibly consult Richmond for this step so we can prepare the right questions to answer

**Tasks**
- Write 10–15 questions a real SME user would ask, covering a spread of documents and topics
- Record the expected answer for each question
- Record the expected source document and section for each question
- Include at least 2 questions that require information from more than one document
- Version the test set inside the repo under `tests/eval/`

**Acceptance Tests**
- Given the golden set is complete, when it is reviewed, then it contains between 10 and 15 question and answer pairs.
- Given any golden pair, when it is inspected, then it records both an expected answer and an expected source document.
- Given the golden set, when the questions are reviewed, then at least 2 require content from more than one document.
- Given the golden set, when the covered topics are listed, then questions span multiple source documents rather than one.

**Definition of Done**
- The test set is committed under `tests/eval/` and reviewed by the H&S lead for realistic phrasing

---

## 11. Record a Terminal Testing Baseline Against the Golden Set

**MoSCoW:** Should | **Est:** 1 day

As a team, we want every golden question run through the terminal script with its retrieval result and latency written down so that Sprints 5 and 6 have a measured starting point to refine against, without standing up the full evaluation suite yet.

**Tasks**
- Run all golden questions from story 10 through the terminal script from story 9
- For each question, record whether the expected source document appeared in the retrieved chunks
- Record response latency per question
- Run the golden set at both 4 and 6 retrieved chunks and record which setting is adopted
- Commit the results as a versioned file under `tests/eval/` alongside the golden set
- Note a suspected cause for any question that fails retrieval

**Acceptance Tests**
- Given the golden Q&A set, when every question is run through the terminal script, then a result is recorded for each one with none skipped.
- Given a golden question, when its result is recorded, then it states whether the expected source document appeared in the retrieved chunks.
- Given any question, when its result is recorded, then the response latency in seconds is recorded against the 5 second target.
- Given the golden set is run at both 4 and 6 retrieved chunks, when the two runs are compared, then the adopted retrieval count is recorded with the reason for choosing it.
- Given a question that failed retrieval, when it is logged, then a suspected cause is recorded following the order: retrieval, chunk quality, system prompt, chunk size.

**Definition of Done**
- Baseline results are committed under `tests/eval/` so the Sprint 5 and Sprint 6 runs can be compared against them
- All questions are ren and the outputs are saved so that Julia (mentor) and Richmond (client) can view

---

## Notes for Sprint Planning

- Stories 1 to 4 are the ingestion track and can run in parallel with early work on 7 and 10, which need no vector store.
- Stories 5 and 6 depend on 2 being complete. Story 9 depends on 6.
- Story 11 depends on 9 and 10, and is the natural drop candidate if the sprint runs tight. If it is dropped, Sprint 6 has no earlier baseline to compare its evaluation run against.
- Formal evaluation tooling (DeepEval, the five capped metrics, per-question scoring against expected answers) is deliberately not in this sprint. It belongs to the Sprint 6 testing suite. Story 11 exists so that sprint has a recorded starting point rather than a blank page.
- The disclaimer in the user interface has been removed from the system prompt story. There is no UI in this sprint, so that requirement moves to the Streamlit sprint.
- Confirmed: the Sprint 1 cleaned output does emit `chunk_type` (values `prose`, `table`, `appendix`, `glossary`), so it stays in story 2.
- Open carry-over from Sprint 1: `scripts/chunking_script.py` runs on a single hardcoded document and its output is not committed. `data/processed/` currently holds cleaned elements, not chunks. Story 2 needs corpus-wide chunked output to exist before it can start.