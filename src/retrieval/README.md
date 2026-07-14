# src/retrieval

The query pipeline: takes a user's question, retrieves the most relevant chunks
from ChromaDB, and runs the LangChain RAG chain to produce a grounded, NZ-
specific answer with a citation.
