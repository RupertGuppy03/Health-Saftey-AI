US-06: Connect Retrieval to LLM — Temporary change log

Summary

This file summarises the temporary, local changes made while implementing US-06: connecting retrieved document chunks to a chat LLM via LangChain. These changes are intended for review and hand-off; they should be merged or cherry-picked into the project branch as part of the normal PR process.

Files added

- src/answer.py
  - Orchestrates retrieval and LLM generation.
  - Handles empty retrievals and OpenAI errors, returning structured payloads: {answer, sources, status, error?}.
  - Exposes build_answer_chain and answer_question.

- src/config/prompts.py
  - Holds the `GROUNDING_SYSTEM_PROMPT` used to instruct the model to answer only from retrieved context and to cite sources. Wording updated for H&S lead review.

- src/api/app.py
  - FastAPI wrapper exposing POST /ask which calls answer_question and returns structured JSON.
  - Dependency `get_llm` allows injection of a stub LLM in tests.

- tests/test_answer_chain.py
  - Unit tests for answer_question: happy path, no-results, OpenAI error handling, and empty-question validation.

- tests/test_api_app.py
  - Integration-style tests for the API endpoint using FastAPI TestClient and dependency overrides. Stubs the retriever and LLM to avoid real API/network calls.

- scripts/run_local_checks.sh
  - Helper script that uses python3 where available to avoid `python: command not found` on systems that expose only `python3`.

- CHANGES_US06_TEMP.md (this file)
  - Temporary summary for sharing with the team.

Files changed

- src/config/settings.py
  - LLM_MODEL now defaults to `gpt-5-mini`.
  - LLM_TEMPERATURE preserved and used when constructing the Chat LLM.

- src/config/prompts.py
  - Prompt text refined to include citation format and output shape for easier review.

- src/answer.py
  - The ChatOpenAI constructor is now tolerant of multiple langchain-openai argument names (tries model_name/openai_api_key then model/api_key).
  - _get_openai_chat_llm accepts and returns injected client instances when provided (allows DI in tests & API overrides).

Notes and next steps

1. Run smoke checks and unit tests locally:
   - ./scripts/run_local_checks.sh
   - python3 -m pytest tests/test_answer_chain.py -q
   - python3 -m pytest tests/test_api_app.py -q

2. Manual verification: populate the ChromaDB vectorstore and run a handful of real queries via the API or terminal script to verify source attributions match the PDFs for at least 5 queries.

3. PR & review: bundle these changes into a feature branch and open a PR so the H&S lead can review the prompt wording and the team can test integration.

4. Clean-up: when this branch is merged, delete this CHANGES_US06_TEMP.md or move its contents into the PR description.

Additions since first draft

- Added the FastAPI run helper: scripts/run_api.sh
- Added an end-to-end style test: tests/test_end_to_end.py which seeds an in-memory ChromaDB collection and runs the /ask endpoint via TestClient without calling external APIs.
- Added PR_DESCRIPTION_US06.md: a suggested PR description and DoD checklist for reviewers.

Acknowledgements

- Implemented by the development automation (Copilot CLI runtime) on behalf of the project team. Do not commit API keys or secrets. Ensure `.env` is populated with `OPEN_AI_API_KEY` or `OPENAI_API_KEY` before running tests that call external APIs.
