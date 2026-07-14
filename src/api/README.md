# src/api

The FastAPI backend that exposes the RAG pipeline. The frontend sends a user's
question to an API endpoint here; the backend runs retrieval + generation and
returns the answer plus its citation.

Kept separate from the UI so the heavy AI work (ChromaDB, embeddings, LangChain)
is decoupled from the frontend and easier to host, test, and scale.
