# Sprint 3 — Streamlit chat UI

Planning docs and user stories for this sprint. Goal: the Streamlit chat UI
connected end-to-end, with session state and error handling. See
[`../Project_User_Stories.md`](../Project_User_Stories.md).

# Sprint 3 — UI & end-to-end integration

Planning docs and user stories for this sprint. Goal: expose the Sprint 2 RAG
pipeline through a FastAPI backend, build the Streamlit chat interface, add
session state, citations, disclaimers and error handling, and prove a working
end-to-end app. See [`../Project_User_Stories.md`](../Project_User_Stories.md).

**Sprint goal:** Connect the RAG pipeline to a usable chat interface so a non-technical user can ask a health and safety question in a browser and get a sourced answer.
**Duration:** 10 sprint days
**Stories:** 11 (9 Must, 2 Should)
**Milestone:** Working end-to-end application

---

## Shared Definition of Done

Applies to every story. Story-specific DoD items are listed under each card in addition to these.

- All acceptance tests pass and are demonstrated to the assigned tester
- Code reviewed by at least one other team member before the card moves to Done
- Code merged to `main` with no broken imports on a clean clone
- Any new environment variable or config value documented in the README
- No API keys, endpoints or secrets committed to the repo
- Any user-facing change is demonstrated live in the browser, not just described
- Burndown chart updated when the card moves to Done

---

## 1. Expose the RAG Pipeline Through a FastAPI Endpoint

**MoSCoW:** Must | **Est:** 2–3 days

As a developer, I want the Sprint 2 pipeline callable over HTTP so that the interface never imports the RAG code directly and the backend can be deployed on its own.

**Tasks**
- Refactor the terminal script pipeline into a reusable function that takes a question and returns answer, sources and latency
- Create a FastAPI application with a `POST /chat` endpoint that accepts a question in the request body
- Define a fixed JSON response shape: `answer`, `sources` (document, page reference, section heading) and `latency_seconds`
- Return a structured error response instead of a stack trace when the pipeline fails
- Document how to start the server locally in the README

**Acceptance Tests**
- Given the server is running, when a question is sent to `POST /chat`, then a JSON response containing an answer and a list of sources is returned.
- Given a successful response, when the sources are inspected, then each entry includes the source document, page reference and section heading.
- Given a request with a missing or empty question, when it is sent, then a validation error with a readable message is returned rather than a crash.
- Given the pipeline raises an error, when the endpoint is called, then an error status code and message are returned rather than a stack trace.
- Given any successful call, when the response is inspected, then response latency in seconds is included.

**Definition of Done**
- The request and response shapes are defined once in a model, not rebuilt per route
- Another team member can start the server and get an answer through the interactive `/docs` page without any UI code running

---

## 2. Load the Pipeline Once at Startup and Add a Health Endpoint

**MoSCoW:** Must | **Est:** 1 day

As a user, I want the vector store and model clients loaded when the server starts so that I do not pay the initialisation cost on every question I ask.

**Tasks**
- Move the ChromaDB client, embedding client and LLM client initialisation to application startup
- Add a `GET /health` endpoint returning service status, collection name and stored chunk count
- Fail clearly at startup if the collection is missing or empty rather than serving empty answers
- Record cold start time and warm query time in the repo

**Acceptance Tests**
- Given the server has started, when `/health` is called, then a success status is returned along with the collection name and stored chunk count.
- Given the server has already answered one question, when a second question is sent, then the vector store is not reloaded.
- Given the persisted collection is missing or empty, when the server starts, then it reports the problem clearly instead of starting silently.
- Given two consecutive questions, when their latencies are compared, then the second is not inflated by re-initialisation.

**Definition of Done**
- `/health` is used as the readiness check by the interface in story 8
- Cold start and warm query timings are recorded in the repo for the deployment phase

---

## 3. Build the Streamlit Chat Interface Shell

**MoSCoW:** Must | **Est:** 2 days

As a user, I want a chat screen where I can type a question and see the conversation so that I can use the assistant without a terminal.

**Tasks**
- Create a Streamlit page with a title, a message area and a chat input pinned at the bottom
- add a download button where users can download their chats in markdown file format
- add a side bar where users can also click on a tab which displays links to all files in the corpus so users can easily see the documents the AI refers to if they want to see for themselves
- Render user and assistant messages as distinct chat bubbles
- Wire the input to a stubbed response so the layout can be built before the backend is connected
- Set the page title, icon and layout width
- Keep all interface code in its own module, separate from pipeline code

**Acceptance Tests**
- Given the app is open, when a question is typed and submitted, then it appears in the message area as a user message.
- Given a submitted question, when the stub replies, then the reply renders as an assistant message directly below it.
- Given several exchanges, when the page is viewed, then user and assistant messages are visually distinguishable and in the order they were sent.
- Given the interface module is inspected, when its imports are reviewed, then no ChromaDB, LangChain or OpenAI code is imported by the interface.

**Definition of Done**
- Layout reviewed by the UX lead before any backend wiring begins
- The app runs on a clean clone with the backend switched off

---

## 4. Connect the Streamlit Interface to the FastAPI Backend

**MoSCoW:** Must | **Est:** 2 days

As a user, I want my question answered by the real pipeline so that the interface returns grounded guidance instead of placeholder text.

**Tasks**
- Replace the stubbed response with an HTTP call to the `/chat` endpoint
- Read the backend URL from configuration or an environment variable rather than hardcoding it
- Render the returned answer in the assistant message
- Confirm the answer displayed matches the answer the API returns for the same question
- Document the two commands needed to run the full app

**Acceptance Tests**
- Given the backend is running, when a question is submitted in the interface, then the answer displayed comes from the backend rather than the stub.
- Given the same question is sent through `/docs` and through the interface, when the two answers are compared, then they use the same retrieved sources.
- Given the backend URL is changed in configuration, when the app is restarted, then the interface calls the new URL with no code change.
- Given five golden questions, when each is run through the interface, then each returns an answer without manual intervention.

**Definition of Done**
- Both services can be started from documented commands by a team member who did not build them
- No API key is present in the interface layer; the backend is the only component holding credentials

---

## 5. Keep Conversation History in Session State

**MoSCoW:** Must | **Est:** 2 days

As a user, I want my conversation to stay on screen as I ask more questions so that I can read back over earlier answers.

**Tasks**
- Store the message history in Streamlit session state
- Re-render the full history on every rerun
- Add a control to clear the conversation and start a new one
- Confirm history is scoped to the browser session and not shared between users
- Guard against the same question being submitted twice on a rerun

**Acceptance Tests**
- Given several completed exchanges, when a new question is submitted, then all earlier messages remain visible and in order.
- Given a widget interaction causes a rerun, when the page redraws, then the existing conversation is preserved rather than cleared.
- Given the clear control is used, when the page redraws, then the message area is empty and a fresh conversation starts.
- Given two browser sessions are open at once, when a question is asked in one, then the other session's history is unaffected.

**Definition of Done**
- No duplicated messages appear in the history after repeated reruns
- Clearing the conversation does not require restarting the app

---

## 6. Show Source Citations for Every Answer

**MoSCoW:** Must | **Est:** 2 days

As a user, I want to see which WorkSafe document each answer came from so that I can check the guidance myself before acting on it.

**Tasks**
- Render the sources returned by the backend underneath each assistant answer
- Show the document name, page reference and section heading for each source
- Collapse repeated chunks from the same document and section into a single entry
- Display a clear message when an answer was returned with no supporting sources
- Format the stored filename into a readable document title rather than showing the raw file name

**Acceptance Tests**
- Given an answer generated from retrieved chunks, when it is displayed, then the sources used are shown with it.
- Given a source entry, when it is read, then it shows the document name, page reference and section heading.
- Given two retrieved chunks from the same document and section, when the sources are displayed, then they appear as one entry rather than two.
- Given no chunks were retrieved, when the response is shown, then the interface states that no supporting guidance was found instead of showing an empty list.

**Definition of Done**
- Citations checked against the source PDFs on at least 5 questions by the H&S lead
- A team member who has not seen the corpus can read a source entry and identify the document

---

## 7. Add Disclaimers and Scope Framing to the Interface

**MoSCoW:** Must | **Est:** 1–2 days

As a user, I want to be told what this assistant is and is not so that I do not mistake general guidance for legal or certified advice.

**Tasks**
- Add a persistent disclaimer stating the assistant provides general guidance, not legal advice or certification
- Build an empty state explaining what the assistant covers and what falls outside it
- Add three to four example questions to the empty state
- State which document set the answers are drawn from so the user knows the basis of the guidance
- Have the wording reviewed by the H&S lead and confirmed with the client

**Acceptance Tests**
- Given the app is opened, when the page loads, then the disclaimer is visible without scrolling or clicking.
- Given a conversation is in progress, when the user scrolls through it, then the disclaimer remains visible or accessible.
- Given a first-time user opens the app, when no question has been asked, then the scope statement and example questions are shown.
- Given any assistant answer, when it is read, then the disclaimer is not repeated inside the answer body.

**Definition of Done**
- Wording signed off by Richmond, or logged in the issue register with an owner if sign-off is still pending
- Disclaimer text lives in one place in config, not duplicated across interface files

---

## 8. Handle Errors and Slow Responses in the Interface

**MoSCoW:** Must | **Est:** 2 days

As a user, I want to see what is happening when something is slow or broken so that the app never appears frozen or crashes in front of me.

**Tasks**
- Show a loading indicator while a question is being processed
- Prevent a second request being sent while one is already in flight
- Handle the backend being unreachable with a plain-language message
- Apply a configurable request timeout and handle it explicitly
- Handle error responses from the backend, including API failures and empty retrieval
- Log the full technical error on the backend while showing a simple message to the user

**Acceptance Tests**
- Given a question is submitted, when the backend is still processing, then a loading indicator is shown until the answer arrives.
- Given the backend is not running, when a question is submitted, then a plain-language message is shown and the app does not crash.
- Given the backend exceeds the configured timeout, when the request fails, then the interface reports that it took too long and invites a retry.
- Given the backend returns an error, when it is displayed, then the user sees plain language while the technical detail is logged on the backend.
- Given a request is already in flight, when the user submits again, then a duplicate request is not sent.

**Definition of Done**
- Every failure path is demonstrated to the tester by deliberately triggering it
- No raw stack trace or Python exception text is ever shown in the browser

---

## 9. Verify the End-to-End App Against the Golden Set

**MoSCoW:** Must | **Est:** 1–2 days

As a team, we want every golden question run through the interface so that the working end-to-end milestone is evidenced rather than assumed.

**Tasks**
- Run all golden questions from the Sprint 2 set through the interface against the running backend
- Record the answer returned, the sources displayed and the end-to-end latency for each
- Compare the results against the Sprint 2 terminal baseline and note any regression
- Capture screenshots for the sprint review and the client demonstration
- Log any failed question in the issue register with an owner

**Acceptance Tests**
- Given the golden set, when every question is run through the interface, then a result is recorded for each one with none skipped.
- Given a recorded result, when it is read, then it states whether the expected source document appeared in the displayed sources.
- Given any question, when its result is recorded, then the end-to-end latency is recorded against the 5 second target.
- Given the results are compared with the terminal baseline, when a question behaves differently, then a suspected cause is recorded.

**Definition of Done**
- Results committed under `tests/eval/` alongside the Sprint 2 baseline so the two can be compared
- Screenshots saved for the sprint review with the client and mentor

---

## 10. Support Follow-Up Questions with Conversation Context

**MoSCoW:** Should | **Est:** 2 days

As a user, I want to ask a follow-up without repeating myself so that the conversation feels natural instead of starting from scratch each time.

**Tasks**
- Send the recent conversation turns to the backend alongside the new question
- Set and document a fixed history limit to control token cost
- Expand a follow-up into a standalone query before retrieval runs
- Confirm the Sprint 2 guardrails still hold once history is included

**Acceptance Tests**
- Given a previous question about a specific topic, when the user asks a follow-up without naming that topic, then the answer stays on the same topic.
- Given a conversation longer than the configured history limit, when a new question is sent, then only the configured number of turns is included.
- Given history is included, when an out-of-scope or adversarial question is asked, then the guardrails behave as they did in Sprint 2 testing.
- Given a follow-up is answered, when the sources are displayed, then they relate to the follow-up rather than the earlier question.

**Definition of Done**
- The history limit is a single configurable value and its token cost impact is recorded
- The Sprint 2 adversarial question set is re-run with history enabled and the results committed

---

## 11. Containerise the Backend with Docker

**MoSCoW:** Should | **Est:** 2 days

As a team, we want the backend running in a container so that the deployment phase starts from a reproducible environment instead of a local machine setup.

**Tasks**
- Write a Dockerfile for the FastAPI backend with pinned dependencies
- Decide and document whether the vector store is built into the image or mounted at runtime
- Pass API keys in as runtime environment variables, never baked into the image
- Confirm the container serves both `/health` and `/chat`
- Document the build and run commands in the README

**Acceptance Tests**
- Given the Dockerfile, when the image is built from a clean clone, then the build completes without manual steps.
- Given the container is running, when `/health` is called, then the collection name and stored chunk count are returned.
- Given the container is running, when the interface is pointed at it, then questions are answered end to end.
- Given the built image, when it is inspected, then no API key or secret is present inside it.

**Definition of Done**
- Another team member builds and runs the container from the documented commands
- The vector store packaging decision is recorded for the deployment phase

---

## 12. Start a New Conversation and Switch Between Session Conversations

**MoSCoW:** could | **Est:** 1–2 days

As a user, I want to start a new conversation without losing the one I was just in so that I can ask about a different topic and still refer back to my earlier questions.

**Tasks**
- Extend the session state store from story 5 to hold multiple conversations rather than a single message list
- Add a "New chat" control that opens an empty conversation and leaves the previous one intact
- List the session's conversations in the sidebar and allow switching between them
- Label each conversation with its first user question, truncated to fit the sidebar
- Add a control to delete a single conversation from the session
- Tell the user plainly in the interface that conversations are not saved once the tab is closed

**Acceptance Tests**
- Given a conversation with several exchanges, when "New chat" is used, then an empty conversation opens and the previous one remains in the sidebar.
- Given more than one conversation exists in the session, when an earlier one is selected, then its full message history is restored in order.
- Given a conversation has at least one user message, when it appears in the sidebar, then it is labelled with that first question rather than a generic name.
- Given a conversation is deleted, when the sidebar redraws, then it is removed and the remaining conversations are unaffected.
- Given the app is opened, when the user views the interface, then it states that conversations are not retained after the tab is closed.

**Definition of Done**
- Switching between conversations does not send any request to the backend or re-run the pipeline
- The non-persistence limitation is recorded in the final report as a scoped decision, with accounts and stored history listed as future work

---

## 13. Ask a Question by Voice

**MoSCoW:** Could | **Est:** 2 days

As a user working on site, I want to speak my question instead of typing it so that I can use the assistant without stopping what I am doing.

**Tasks**
- Add an audio recording control to the interface alongside the existing text input
- Add a transcription endpoint on the backend that accepts audio and returns text
- Show the transcript in the input area so the user can correct it before sending
- Send the confirmed transcript through the existing `/chat` endpoint with no separate answer path
- Handle empty, silent or failed recordings with a plain-language message
- Record the transcription cost per query against the remaining API budget

**Acceptance Tests**
- Given a recorded question, when the recording is submitted, then a transcript is returned and displayed before anything is sent to the pipeline.
- Given a displayed transcript, when the user edits it and sends, then the edited text is what reaches the `/chat` endpoint.
- Given a spoken question and the same question typed, when both are answered, then the answers use the same retrieved sources.
- Given an empty or silent recording, when it is submitted, then the interface reports that nothing was heard and does not call the pipeline.
- Given transcription fails, when the error is handled, then the user is told and the text input remains fully usable.

**Definition of Done**
- Voice is input only; no spoken response is generated in this sprint
- Transcription accuracy is spot checked on at least 10 spoken health and safety questions, including terms specific to the corpus
- Measured transcription cost is recorded against the API budget before the feature is kept

## Notes for Sprint Planning

- Story 1 blocks 2, 4 and 8. Story 3 uses a stubbed response, so interface work can start in parallel with the backend from day one rather than waiting on it.
- Stories 5, 6 and 7 can run in parallel once 4 is done. Story 7 needs no backend at all and is a good fit for whoever is blocked.
- Story 9 depends on everything else and should be scheduled into the last two days of the sprint. It is the evidence for the working end-to-end milestone, so it is not a drop candidate.
- Stories 10 and 11 are the drop candidates. If 10 is dropped, the app answers each question independently and follow-ups must be phrased in full, which should be noted in the sprint review as a known limitation. If 11 is dropped, the deployment phase starts with a local-only backend.
- Any unfinished Sprint 2 stories carry into this sprint and are pulled in before either Should story is started.
- Formal evaluation tooling stays out of this sprint. Story 9 is a manual walkthrough for the milestone, not the evaluation suite.
- The interface disclaimer requirement was deliberately moved out of the Sprint 2 system prompt story into this sprint. It is now story 7.
- The backend is FastAPI rather than Streamlit-only, which is a deviation from the original proposal. The project documentation needs updating to reflect this before the final report.
