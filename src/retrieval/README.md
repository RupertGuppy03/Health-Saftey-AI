# src/retrieval

The query pipeline: takes a user's question, retrieves the most relevant chunks
from ChromaDB, and runs the LangChain RAG chain to produce a grounded, NZ-
specific answer with a citation.

`retriever.py` is the retrieval half of that: `retrieve(question)` embeds the
question with the ingestion model and returns the nearest chunks with the
metadata a citation needs. It only reads the collection — it never writes to it
or re-embeds a document. How many chunks come back is `RETRIEVAL_TOP_K` in
`src/config/settings.py`.

The LangChain chain and the system prompt land here next, alongside it.
