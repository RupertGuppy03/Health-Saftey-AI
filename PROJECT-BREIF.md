# Project Brief: Health & Safety AI Compliance Chatbot

## What This Is

A Retrieval-Augmented Generation (RAG) chatbot that helps New Zealand small and medium businesses understand and apply workplace health and safety requirements. Users ask questions in plain language and get accurate, context-specific guidance grounded in official NZ sources, with citations back to the source document and page. It also identifies workplace hazards from user descriptions and suggests risk mitigation strategies. The product is web-based, built to feel like a ChatGPT-style chat interface.

## Scope

In scope: a web app with a chat interface, a RAG pipeline grounded in NZ legislation and WorkSafe guidance, source citations, hazard identification with mitigation suggestions, and the ability to distinguish general guidance from legal advice (with disclaimers). Construction is the primary industry for hazard detection in v1.

Out of scope: legal or professional certification of workplace safety, a mobile app (web browser only), integration with external business systems, user authentication/accounts, and any maintenance past project submission.

## Team Roles

Rupert Guppy, Product Owner and AI/Technical Development Lead. Defines technical requirements, leads AI system development, and makes sure the app meets its functional and non-functional requirements.

Jerseyleigh Gallardo (Leigh), Scrum Master and Project Manager. Coordinates the team, tracks progress and risks, runs sprint reviews and retrospectives, and oversees QA and documentation.

Luca Genet, Developer and User Experience Lead. Owns the Streamlit UI design, usability testing, and interaction quality. Also contributed to defining the RAG-specific performance metrics.

Theo Meer, Developer and Health and Safety Lead. Ensures outputs align with NZ health and safety guidance, owns data preparation and domain accuracy, and writes the known-answer test scenarios used for validation.

## Tech Stack

Python throughout. OpenAI API (GPT-4o / GPT-4.1) as the LLM. LangChain for orchestration. ChromaDB as the vector store, persisted to disk. OpenAI embeddings. PyMuPDF or pdfplumber for PDF text extraction. Streamlit for the frontend. FastAPI to expose the RAG backend to the frontend. Docker for containerising the backend. pytest for unit tests and DeepEval for AI evaluation. GitHub for version control.

## How It's Built (Pipeline)

Raw WorkSafe NZ PDFs and the Health and Safety at Work Act 2015 are collected into the repo. A processing pipeline extracts clean text (stripping headers, footers, page numbers, and boilerplate programmatically rather than editing PDFs by hand), then chunks the text. Each chunk is stored with metadata: document title, page number, and industry category. Chunks are embedded and stored in ChromaDB. At query time, the retriever pulls relevant chunks, LangChain feeds them plus the system prompt to the LLM, and the response is returned with a citation. The system prompt enforces grounding, NZ-specific answers, and the "not legal advice" disclaimer.

## API and Backend

The RAG pipeline is exposed through a FastAPI backend rather than being called directly inside the Streamlit app. The frontend sends a user query to an API endpoint, the backend runs retrieval and generation, and the response plus citation is returned to the frontend. Keeping the backend separate means the heavy AI workload (ChromaDB, embeddings, LangChain) is decoupled from the UI, which makes it easier to host, test, and scale independently.

## Deployment and Hosting

The exact deployment setup will be finalised during the deployment phase, but the plan is to containerise the backend using Docker so it can be hosted somewhere with enough resources for the RAG workload, such as Azure or AWS. This is because Streamlit Community Cloud caps apps at 1 GB of RAM, which may not be enough for the full pipeline. The frontend can still be hosted on Streamlit Community Cloud if that works, or bundled with the backend, whichever proves simplest at deployment time. Nothing here is locked in yet, the Docker container just keeps hosting options open.

## Sprints

Sprint 0 (environment setup): GitHub, Streamlit, API integration.

Sprint 1: document sourcing and the extract/chunk pipeline, with pytest tests.

Sprint 2: embeddings, ChromaDB setup, core RAG pipeline in LangChain, system prompt, terminal testing, latency timer.

Sprint 3: Streamlit chat UI connected end-to-end, session state, error handling.

Sprint 4: hazard detection and mitigation, out-of-scope query handling, construction document tagging.

Sprint 5: usability and performance, reducing hallucinations, latency optimisation, user testing.

Sprint 6: full evaluation run, system testing, UAT with client. Get the final project running locally, including feedback from users and the client.

Deployment and handover phase: deploy the solution, ensuring the Docker container and FastAPI backend are wired up before handing over to the client.

## Accuracy and Testing Plan

Five capped evaluation metrics run via DeepEval. Three generic RAG metrics: Faithfulness, Answer Relevancy, Contextual Relevancy (target above 0.9 each). Two custom metrics: G-Eval for helpfulness and plain-language quality (target above 0.85), and DAG for citation accuracy, which checks a citation exists and that the cited source/page matches the retrieved chunk's ChromaDB metadata (must pass the decision tree). From Sprint 2 onward, lightweight metrics (response latency, answer alignment) are tracked each sprint. Full five-metric validation plus UAT happens in Sprint 6.

Response speed is a goal, not a hard requirement: the team aims for sub-5-second responses but treats this as a target to work toward rather than a pass/fail threshold.