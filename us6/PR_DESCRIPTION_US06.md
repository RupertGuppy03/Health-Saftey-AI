PR: US-06 — Connect Retrieval to LLM via LangChain

This PR implements the retrieval→LLM chain and supporting infrastructure for US-06.

Summary of changes

- Adds src/answer.py: orchestration layer that retrieves relevant chunks from ChromaDB, formats context, calls the chat LLM via LangChain, and returns structured results including source metadata.
- Adds src/config/prompts.py: system prompt with grounding and citation instructions for the H&S assistant.
- Adds src/api/app.py: FastAPI wrapper exposing POST /ask to run the full RAG pipeline.
- Adds tests:
  - tests/test_answer_chain.py (unit tests for the answer generation flow)
  - tests/test_api_app.py (API-level tests using TestClient with stubbed LLM/retriever)
  - tests/test_end_to_end.py (integration-style test seeding an in-memory ChromaDB collection and running through the API)
- Adds scripts/run_local_checks.sh and scripts/run_api.sh for local development convenience.
- Updates README.md with instructions to run the smoke checks and unit tests.
- Adds CHANGES_US06_TEMP.md summarising the work for reviewers.

Acceptance criteria mapping

- Given retrieved chunks, when the chain runs, then the LLM returns an answer that uses the retrieved content: Covered by tests/test_end_to_end.py and tests/test_api_app.py (happy path).
- Given an answer has been generated, when response is inspected, then the source documents and sections used are returned alongside the answer: The API returns `sources` matching Chroma metadata; tests assert the returned sources.
- Given retrieval returns no chunks, when the chain runs, then the system reports that no relevant information was found instead of generating an answer: Covered by tests/test_api_app.py (no-results case) and answer_question returns status no_results.
- Given the OpenAI API returns an error, when the chain runs, then the error is caught and reported rather than crashing: Covered by tests/test_answer_chain.py and tests/test_api_app.py (LLM error case).

Definition of Done checklist

- [x] Source attribution is returned and test-asserted in unit/integration tests.
- [x] Metadata passed through the chain matches the metadata stored in ChromaDB (tests inspect `sources`).
- [x] No-hit and API-error flows are handled and tested.
- [x] Prompt stored in src/config/prompts.py for H&S lead review.
- [x] Local run scripts included and README updated.

Testing notes

- The tests stub or seed ChromaDB and the embedding step so CI does not call external services.
- For manual validation, run the ingestion to populate `vectorstore/`, then start the API with scripts/run_api.sh and query /ask.

Request to reviewers

- H&S lead: please review src/config/prompts.py for language suitability and the citation format.
- Dev: please run the tests and confirm the behavior against a local seeded vectorstore if possible.
