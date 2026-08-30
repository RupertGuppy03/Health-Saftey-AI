"""Find the document chunks most relevant to a user's question.

The read side of the pipeline: a question goes in, the nearest chunks come back
with the metadata needed to cite them. Nothing here writes to the collection or
re-embeds the corpus — the only thing this module ever sends to OpenAI is the
question itself.

    retrieve("What edge protection do I need on a roof?")

Deliberately independent of the ingestion code. It shares the embedding model
with ingestion through src.config.settings, which is what makes the query vector
and the stored vectors comparable, and reaches the collection through
src.vectorstore_client.
"""

import os

from dotenv import load_dotenv
from openai import OpenAI

from src.config.settings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    RETRIEVAL_RELEVANCE_THRESHOLD,
    RETRIEVAL_TOP_K,
)
from src.vectorstore_client import get_collection


# Shown in place of a heading for the front-matter chunks that have none.
FALLBACK_SECTION_HEADING = "(no section heading)"


# =====================================================
# EMBEDDING THE QUERY
# =====================================================


def _get_openai_client():
    """Build an OpenAI client from whichever key name is in the .env.

    The project's .env uses OPEN_AI_API_KEY, but the OpenAI SDK only auto-reads
    OPENAI_API_KEY. Accept either so nobody has to edit their local .env.
    """

    load_dotenv(override=True)

    api_key = os.environ.get("OPEN_AI_API_KEY") or os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "No OpenAI API key found. Set OPEN_AI_API_KEY "
            "(or OPENAI_API_KEY) in your .env file."
        )

    return OpenAI(api_key=api_key)


def embed_query(question, client=None):
    """Embed one question with EMBEDDING_MODEL, the model used at ingestion.

    Same model, same width, no truncation — a query embedded any other way is
    not comparable to what is stored and would return meaningless neighbours.
    Pass `client` to inject a stub in tests and avoid hitting the real API.
    """

    if not question or not question.strip():
        raise ValueError("Cannot embed an empty question")

    if client is None:
        client = _get_openai_client()

    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[question],
    )

    vector = response.data[0].embedding

    # Fail here rather than let Chroma reject the query with a dimension error
    # that says nothing about which side is wrong.
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSIONS}-dimension vectors from "
            f"{EMBEDDING_MODEL}, got {len(vector)}"
        )

    return vector


# =====================================================
# RETRIEVAL
# =====================================================


def _result_record(rank, chunk_id, text, metadata, distance):
    """One retrieved chunk, flattened out of Chroma's parallel lists.

    source_file / page_number / section_heading are the locked Sprint 1 schema
    and are what a citation is built from. chunk_type is optional — ingestion
    only stores it when the chunk file carries one.
    """

    metadata = metadata or {}
    distance = 0.0 if distance is None else float(distance)
    similarity_score = max(0.0, 1.0 - distance)

    return {
        "rank": rank,
        "chunk_id": chunk_id,
        "text": text or "",
        "source_file": metadata.get("source_file", ""),
        "page_number": metadata.get("page_number"),
        "section_heading": metadata.get("section_heading", ""),
        "chunk_type": metadata.get("chunk_type"),
        "distance": distance,
        "similarity_score": similarity_score,
    }


def _distance_to_similarity(distance):
    """Convert Chroma cosine distance to a simple 0..1 similarity score.

    Chroma's `distances` are lower-is-better, so this approximates the common
    similarity formula used in retrieval evaluation: similarity = 1 - distance.
    """

    if distance is None:
        return 0.0

    distance = float(distance)
    return max(0.0, 1.0 - distance)


def retrieve(question, n_results=RETRIEVAL_TOP_K, collection_name=None, client=None):
    """Return the chunks nearest to the question, nearest first.

    NOTE: the collection stores 1536-dimension OpenAI vectors, but Chroma still
    has its own built-in 384-dimension embedder attached. Passing query_texts=
    would use that built-in model and fail on a dimension mismatch, so the
    question is embedded here and handed over as query_embeddings=.

    An empty collection returns an empty list rather than raising — reporting
    that nothing relevant was found is the caller's decision, not this one's.
    """

    collection = get_collection(collection_name)

    # Chroma raises if asked for more than it holds.
    wanted = min(n_results, collection.count())

    if wanted < 1:
        return []

    query_vector = embed_query(question, client=client)

    response = collection.query(
        query_embeddings=[query_vector],
        n_results=wanted,
        include=["documents", "metadatas", "distances"],
    )

    # query() answers a list of queries, so every field is a list of lists and
    # we only ever ask about one question.
    ids = response["ids"][0]
    documents = response["documents"][0]
    metadatas = response["metadatas"][0]
    distances = response["distances"][0]

    results = []
    for rank, (chunk_id, text, metadata, distance) in enumerate(
        zip(ids, documents, metadatas, distances), start=1
    ):
        record = _result_record(rank, chunk_id, text, metadata, distance)
        if _distance_to_similarity(record["distance"]) < RETRIEVAL_RELEVANCE_THRESHOLD:
            continue
        results.append(record)

    return results


# =====================================================
# OUTPUT
# =====================================================


def format_results(results, text_chars=300):
    """Render retrieved chunks as plain text for the notebook and terminal.

    Every chunk is printed with the source it came from, so retrieval quality
    can be judged against the PDFs by eye.
    """

    if not results:
        return "  No chunks retrieved."

    lines = []

    for result in results:
        heading = result["section_heading"] or FALLBACK_SECTION_HEADING

        lines.append(
            f"  [{result['rank']}] {result['source_file']}"
            f"  page {result['page_number']}  (distance {result['distance']:.4f})"
        )
        lines.append(f"      section: {heading}")

        text = " ".join(result["text"].split())

        if len(text) > text_chars:
            text = text[:text_chars].rstrip() + "..."

        lines.append(f"      {text}")
        lines.append("")

    return "\n".join(lines).rstrip()
