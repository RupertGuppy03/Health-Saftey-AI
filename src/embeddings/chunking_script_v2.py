"""Chunk cleaned documents and ingest them into the persisted ChromaDB collection.

Two stages, usable independently:

    chunk_document(...)      cleaned elements JSON -> chunk records JSON
    ingest_to_chromadb(...)  chunk records JSON -> embedded + stored in Chroma

Embeddings come from OpenAI's text-embedding-3-small at its native 1536
dimensions. Chroma is only the store: we hand it finished vectors rather than
letting it embed anything itself.
"""

import json
import os
from collections import defaultdict
from pathlib import Path

import tiktoken
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI

from src.config.settings import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MAX_TOKENS_PER_REQUEST,
    EMBEDDING_MODEL,
    PIPELINE_VERSION,
)
from src.vectorstore_client import get_collection


# Used when a cleaned record has no section heading at all (front matter that
# appears before the document's first Title element).
FALLBACK_SECTION_HEADING = "(no section heading)"

# Chroma rejects a single add/upsert larger than roughly 5,461 records, and the
# full corpus is ~5,400 chunks. Stay comfortably under it.
MAX_UPSERT_BATCH = 5000


# =====================================================
# SPRINT 1 - CHUNKING
# =====================================================

def chunk_document(
    input_file,
    output_file,
    chunk_size=4000,
    chunk_overlap=800,
):
    """
    Reconstruct sections from cleaned JSON
    and generate chunks.
    """

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Total records: {len(data)}")

    grouped_sections = defaultdict(list)

    for item in data:
        key = (
            item["source_file"],
            _resolve_section_heading(item),
        )
        grouped_sections[key].append(item)

    reconstructed_sections = []

    for (source_file, section_heading), items in grouped_sections.items():

        combined_text = " ".join(
            item["text"].strip()
            for item in items
            if item["text"].strip()
        )

        page_numbers = sorted(
            set(item["page_number"] for item in items)
        )

        section_data = {
            "source_file": source_file,
            "section_heading": section_heading,
            "page_numbers": page_numbers,
            "text": combined_text,
        }

        # Preserve chunk_type if source data contains it
        chunk_types = {
            item.get("chunk_type")
            for item in items
            if item.get("chunk_type")
        }

        if len(chunk_types) == 1:
            section_data["chunk_type"] = list(chunk_types)[0]

        reconstructed_sections.append(section_data)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n",
            "\n",
            ". ",
            " ",
        ],
    )

    chunked_output = []
    chunk_counter = 1

    for section in reconstructed_sections:

        chunks = splitter.split_text(section["text"])

        for chunk in chunks:

            chunk_record = {
                "chunk_id": f"CHUNK_{chunk_counter:05}",
                "text": chunk,
                "source_file": section["source_file"],
                "page_number": min(section["page_numbers"]),
                "section_heading": section["section_heading"],
            }

            if "chunk_type" in section:
                chunk_record["chunk_type"] = section["chunk_type"]

            chunked_output.append(chunk_record)

            chunk_counter += 1

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            chunked_output,
            f,
            indent=4,
            ensure_ascii=False,
        )

    print(f"Chunks created: {len(chunked_output)}")
    print("Saved successfully")

    return chunked_output


def _resolve_section_heading(item):
    """Section heading for a record, never empty.

    A few records (front matter appearing before the document's first Title)
    have no heading. They get a neutral placeholder rather than being folded
    into whichever heading happens to come next, which in several documents is
    an unrelated acknowledgements entry. source_file still identifies the
    document for citation purposes.
    """

    heading = (item.get("section_heading") or "").strip()

    return heading or FALLBACK_SECTION_HEADING


# =====================================================
# VALIDATION
# =====================================================

def validate_chunks(chunked_output):

    required_fields = [
        "chunk_id",
        "text",
        "source_file",
        "page_number",
        "section_heading",
    ]

    for chunk in chunked_output:
        for field in required_fields:

            if field not in chunk:
                raise ValueError(
                    f"Missing field '{field}' "
                    f"for chunk {chunk.get('chunk_id')}"
                )

            value = chunk[field]

            if value is None:
                raise ValueError(
                    f"Null value for '{field}' "
                    f"on chunk {chunk.get('chunk_id')}"
                )

            if isinstance(value, str) and not value.strip():
                raise ValueError(
                    f"Empty value for '{field}' "
                    f"on chunk {chunk.get('chunk_id')}"
                )

    print("Chunk validation successful")


# =====================================================
# SPRINT 2 - OPENAI EMBEDDINGS
# =====================================================

def _get_openai_client():
    """Build an OpenAI client from whichever key name is in the .env.

    The project's .env uses OPEN_AI_API_KEY, but the OpenAI SDK only auto-reads
    OPENAI_API_KEY. Accept either so nobody has to edit their local .env.
    """

    load_dotenv(override=True)

    api_key = (
        os.environ.get("OPEN_AI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )

    if not api_key:
        raise RuntimeError(
            "No OpenAI API key found. Set OPEN_AI_API_KEY "
            "(or OPENAI_API_KEY) in your .env file."
        )

    return OpenAI(api_key=api_key)


def _split_into_batches(texts, batch_size):
    """Group texts into API-sized batches, capped by count and by tokens."""

    encoding = tiktoken.get_encoding("cl100k_base")

    batches = []
    current = []
    current_tokens = 0

    for text in texts:

        text_tokens = len(encoding.encode(text))

        full_by_count = len(current) >= batch_size

        full_by_tokens = (
            current
            and current_tokens + text_tokens > EMBEDDING_MAX_TOKENS_PER_REQUEST
        )

        if full_by_count or full_by_tokens:
            batches.append(current)
            current = []
            current_tokens = 0

        current.append(text)
        current_tokens += text_tokens

    if current:
        batches.append(current)

    return batches


def embed_texts(
    texts,
    batch_size=EMBEDDING_BATCH_SIZE,
    client=None,
):
    """Embed a list of strings, batching the API calls.

    Returns one vector per input text, in the same order as the input.
    Pass `client` to inject a stub in tests and avoid hitting the real API.
    """

    if not texts:
        return []

    if client is None:
        client = _get_openai_client()

    batches = _split_into_batches(texts, batch_size)

    embeddings = []

    for batch_number, batch in enumerate(batches, start=1):

        print(
            f"  embedding batch {batch_number}/{len(batches)} "
            f"- {len(batch)} texts"
        )

        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )

        # The API does not promise response order, so sort by the echoed index
        # rather than assuming it lines up with the request.
        for item in sorted(response.data, key=lambda d: d.index):

            if len(item.embedding) != EMBEDDING_DIMENSIONS:
                raise ValueError(
                    f"Expected {EMBEDDING_DIMENSIONS}-dimension vectors from "
                    f"{EMBEDDING_MODEL}, got {len(item.embedding)}"
                )

            embeddings.append(item.embedding)

    if len(embeddings) != len(texts):
        raise ValueError(
            f"Embedded {len(embeddings)} vectors "
            f"for {len(texts)} texts"
        )

    return embeddings


# =====================================================
# SPRINT 2 - CHROMADB INGESTION
# =====================================================

def _chunk_record_id(source_file, page_number, index):
    """Deterministic Chroma ID: filename stem, page, position in the document.

    Computed from the data rather than assigned by a counter, so the same chunk
    file always produces the same IDs. The stem keeps documents from colliding;
    the index keeps chunks on the same page apart.
    """

    return f"{Path(source_file).stem}:p{int(page_number):04d}:{index:04d}"


def build_chunk_ids(chunks):
    """One deterministic ID per chunk, in chunk-file order."""

    return [
        _chunk_record_id(chunk["source_file"], chunk["page_number"], index)
        for index, chunk in enumerate(chunks)
    ]


def _chunk_metadata(chunk, chunk_size, chunk_overlap):
    """Metadata stored alongside a chunk.

    The first four fields are the locked Sprint 1 schema. The rest record which
    pipeline produced the vector, so stale embeddings can be spotted after a
    config change.
    """

    metadata = {
        "source_file": chunk["source_file"],
        "page_number": chunk["page_number"],
        "section_heading": chunk["section_heading"],
        "pipeline_version": PIPELINE_VERSION,
        "embedding_model": EMBEDDING_MODEL,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
    }

    if chunk.get("chunk_type"):
        metadata["chunk_type"] = chunk["chunk_type"]

    return metadata


def _prune_stale_records(collection, source_files, current_ids):
    """Delete records for these documents that this run did not produce.

    upsert only overwrites IDs that still exist. If a chunking change makes a
    document yield fewer chunks than before, the leftovers would stay in the
    collection and keep being retrieved. Removing them is what keeps a re-run
    a true replacement rather than an accumulation.
    """

    current = set(current_ids)
    removed = 0

    for source_file in sorted(source_files):

        existing = collection.get(
            where={"source_file": source_file},
            include=[],
        )["ids"]

        stale = sorted(set(existing) - current)

        if stale:
            collection.delete(ids=stale)
            removed += len(stale)

    return removed


def ingest_to_chromadb(
    chunk_file,
    collection_name=None,
    batch_size=EMBEDDING_BATCH_SIZE,
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    client=None,
):
    """Embed a chunk file with OpenAI and upsert it into the named collection.

    Safe to re-run. Chunk IDs are deterministic, so a repeat run upserts over
    the same records instead of appending, and any record this run no longer
    produces is pruned. The collection name and on-disk location come from
    src.config.settings via the vector store client.

    NOTE: the collection stores 1536-dimension OpenAI vectors, but Chroma still
    has its own built-in 384-dimension embedder attached. Querying this
    collection with query_texts= would use that built-in model and fail with a
    dimension mismatch. Always embed the query with embed_texts() and pass
    query_embeddings= instead.
    """

    print("Loading chunk file...")

    with open(chunk_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    validate_chunks(chunks)

    print(f"Embedding {len(chunks)} chunks with {EMBEDDING_MODEL}...")

    embeddings = embed_texts(
        [chunk["text"] for chunk in chunks],
        batch_size=batch_size,
        client=client,
    )

    collection = get_collection(collection_name)

    count_before = collection.count()

    ids = build_chunk_ids(chunks)
    documents = [chunk["text"] for chunk in chunks]
    metadatas = [
        _chunk_metadata(chunk, chunk_size, chunk_overlap)
        for chunk in chunks
    ]

    print(f"Upserting into collection '{collection.name}'...")

    for start in range(0, len(ids), MAX_UPSERT_BATCH):

        end = start + MAX_UPSERT_BATCH

        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            embeddings=embeddings[start:end],
            metadatas=metadatas[start:end],
        )

    source_files = {chunk["source_file"] for chunk in chunks}

    stale_removed = _prune_stale_records(collection, source_files, ids)

    if stale_removed:
        print(f"Pruned {stale_removed} stale record(s) from a previous run")

    count_after = collection.count()

    summary = {
        "collection": collection.name,
        "chunks_embedded": len(chunks),
        "stale_removed": stale_removed,
        "count_before": count_before,
        "count_after": count_after,
        "embedding_model": EMBEDDING_MODEL,
        "pipeline_version": PIPELINE_VERSION,
    }

    print(
        f"Stored {len(chunks)} chunks. "
        f"Collection count {count_before} -> {count_after}"
    )

    return summary
