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
import re
from pathlib import Path

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

from src.config.settings import (
    CHUNK_MAX_CHARS,
    CHUNK_MIN_CHARS,
    CHUNK_OVERLAP_CHARS,
    CHUNK_TARGET_CHARS,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MAX_TOKENS_PER_REQUEST,
    EMBEDDING_MODEL,
    HEADING_STRUCTURAL_SHARE,
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

# A heading like "1.3" or "2." — a structural signal, not a topic word.
NUMBERED_HEADING = re.compile(r"^\s*\d+(\.\d+)*[\.\)\s]")


def _is_all_caps(text):
    letters = [c for c in text if c.isalpha()]

    if not letters:
        return False

    return sum(c.isupper() for c in letters) / len(letters) > 0.8


def _is_structural_heading(text):
    """A numbered heading, or a short ALL CAPS line.

    These are strong, unambiguous formatting signals. Nothing here looks at
    subject matter, so it behaves the same on any document.
    """

    text = text.strip()

    return bool(NUMBERED_HEADING.match(text)) or (
        _is_all_caps(text) and len(text) <= 80
    )


def _looks_like_heading_shape(text):
    """A short capitalised line that does not read as part of a sentence.

    Looser than the structural test, for documents that write their headings in
    Title Case. Sentence fragments are rejected because they either start
    lower-case or end in sentence punctuation.
    """

    text = text.strip()

    if not text or len(text) > 80:
        return False

    if not text[:1].isupper():
        return False

    if text.rstrip().endswith((".", ",", ";", ":")):
        return False

    return len(text.split()) <= 10


def detect_allow_heading_shape(records):
    """Whether this document needs the looser Title Case heading rule.

    Documents differ in house style: some number their headings or set them in
    caps, others use Title Case. Measure which convention this document actually
    follows instead of assuming one for the whole corpus.
    """

    titles = [
        record["text"].strip()
        for record in records
        if record.get("element_type") == "Title" and record["text"].strip()
    ]

    if not titles:
        return True

    structural_share = sum(
        _is_structural_heading(text) for text in titles
    ) / len(titles)

    # A clear structural convention means anything else is probably a stray
    # Title, so do not widen the net.
    return structural_share < HEADING_STRUCTURAL_SHARE


def _ends_a_sentence(text):
    """Whether this text reads as a complete sentence, not a continuation."""

    return text.rstrip().endswith((".", "!", "?"))


def is_section_heading(text, allow_shape, previous_text=""):
    """Whether this text should start a new section.

    A numbered or ALL CAPS heading is accepted unconditionally — that
    formatting is unambiguous regardless of context. The looser Title Case
    rule additionally requires the previous element to read as a finished
    sentence, otherwise a short capitalised fragment from a line-wrapped
    sentence (e.g. a name or place starting a new line) would be mistaken for
    a heading — the failure mode a fixed keyword or shape rule alone cannot
    catch, since the fragment itself looks exactly like a valid short heading.
    """

    if _is_structural_heading(text):
        return True

    if not allow_shape or not _looks_like_heading_shape(text):
        return False

    return not previous_text or _ends_a_sentence(previous_text)


def _split_table_text(text, max_chars):
    """Split an oversized markdown table on row boundaries, repeating the header.

    Every part has to stand on its own, so each carries the header row and its
    `| --- |` separator.
    """

    lines = text.split("\n")

    if len(text) <= max_chars or len(lines) < 3:
        return [text]

    header = lines[:2]
    header_text = "\n".join(header)

    parts = []
    current = list(header)

    for line in lines[2:]:

        candidate = "\n".join(current + [line])

        if len(candidate) > max_chars and len(current) > len(header):
            parts.append("\n".join(current))
            current = list(header)

        current.append(line)

    if len(current) > len(header):
        parts.append("\n".join(current))

    return parts or [header_text]


def _build_chunk_record(elements, section_heading, chunk_number, chunk_type=None):
    """Turn a run of elements into one chunk record."""

    pages = [
        element["page_number"]
        for element in elements
        if element.get("page_number") is not None
    ]

    page_start = min(pages) if pages else None
    page_end = max(pages) if pages else None

    if chunk_type is None:
        types = [e.get("chunk_type") for e in elements if e.get("chunk_type")]
        chunk_type = types[0] if types else "prose"

    return {
        "chunk_id": f"CHUNK_{chunk_number:05}",
        "text": " ".join(e["text"].strip() for e in elements if e["text"].strip()),
        "source_file": elements[0]["source_file"],
        # page_number stays as the locked US-09 field name and equals page_start.
        "page_number": page_start,
        "page_start": page_start,
        "page_end": page_end,
        "section_heading": section_heading,
        "chunk_type": chunk_type,
    }


def _overlap_tail(elements, overlap_chars):
    """Trailing elements of a chunk, to repeat at the start of the next one.

    Whole elements rather than a character slice, so a chunk never opens
    mid-sentence.
    """

    tail = []
    size = 0

    for element in reversed(elements):

        if size >= overlap_chars:
            break

        tail.insert(0, element)
        size += len(element["text"])

    return tail


def chunk_document(
    input_file,
    output_file,
    target_chars=CHUNK_TARGET_CHARS,
    max_chars=CHUNK_MAX_CHARS,
    min_chars=CHUNK_MIN_CHARS,
    overlap_chars=CHUNK_OVERLAP_CHARS,
):
    """Pack cleaned elements into chunks, in document order.

    Elements arrive far too small to embed on their own — around half the corpus
    is under 50 characters — so they are accumulated until the chunk is worth
    retrieving. Section headings are preferred break points but never form a
    chunk by themselves, and tables are emitted whole.
    """

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Total records: {len(data)}")

    allow_shape = detect_allow_heading_shape(data)

    chunks = []
    # Parallel to `chunks`: the source elements behind each chunk, needed to
    # compute the overlap tail and to extend a chunk if it is later merged into.
    chunk_elements = []

    buffer = []
    buffer_chars = 0
    carried = 0  # leading elements of `buffer` that are last chunk's overlap tail
    section_heading = FALLBACK_SECTION_HEADING
    buffer_heading = FALLBACK_SECTION_HEADING
    previous_text = ""

    def flush(before_table=False):
        nonlocal buffer, buffer_chars, carried, buffer_heading

        new_elements = buffer[carried:]

        if not new_elements:
            # Nothing beyond the carried-over tail — that text is already in
            # the previous chunk, so there is nothing to emit or merge.
            buffer, buffer_chars, carried = [], 0, 0
            return None

        too_small = buffer_chars < min_chars
        can_merge_back = (
            bool(chunks)
            and chunks[-1]["chunk_type"] != "table"
            # Folding in would still have to respect the hard ceiling — a
            # fragment that would push the previous chunk over max_chars is
            # better left standalone than silently breaking the cap.
            and len(chunks[-1]["text"]) + buffer_chars <= max_chars
        )
        # A pending run counts as a table caption only if it does not read as
        # a finished sentence — a label like "Sampling information:", a run of
        # heading fragments, or a form-style lead-in, none of which stand on
        # their own but all of which belong with the table that follows.
        # Genuine prose (which ends in . ! or ?, even when short) is left to
        # the standard too-small handling below instead of being glued onto
        # an unrelated table.
        reads_as_caption = not _ends_a_sentence(new_elements[-1]["text"])

        if too_small and before_table and reads_as_caption and not can_merge_back:
            # A heading-only lead-in with no chunk it can fold backward into —
            # typically a checklist label immediately followed by its table,
            # with nothing before it but another table. Hand the text back to
            # the caller to prepend onto the table instead of emitting it as
            # its own fragment.
            caption = " ".join(e["text"].strip() for e in new_elements if e["text"].strip())
            buffer, buffer_chars, carried = [], 0, 0
            return caption or None

        if too_small and can_merge_back:
            # Too small to stand alone. Fold the new part into the previous
            # chunk rather than emitting a fragment.
            previous = chunks[-1]
            extra = " ".join(e["text"].strip() for e in new_elements if e["text"].strip())

            if extra:
                previous["text"] = f"{previous['text']} {extra}".strip()

            pages = [e["page_number"] for e in new_elements if e.get("page_number") is not None]

            if pages:
                previous["page_end"] = max(pages + ([previous["page_end"]] if previous["page_end"] is not None else []))

            chunk_elements[-1].extend(new_elements)
            source_elements = chunk_elements[-1]
        else:
            chunks.append(_build_chunk_record(buffer, buffer_heading, len(chunks) + 1))
            chunk_elements.append(list(buffer))
            source_elements = buffer

        tail = _overlap_tail(source_elements, overlap_chars) if overlap_chars else []
        buffer = list(tail)
        buffer_chars = sum(len(e["text"]) for e in buffer)
        carried = len(buffer)
        buffer_heading = section_heading
        return None

    for element in data:

        text = element["text"].strip()

        if not text:
            continue

        # element_type, not chunk_type: classify_chunk_type() returns
        # "appendix"/"glossary" for tables under those headings, so chunk_type
        # cannot be used to recognise a table.
        if element.get("element_type") == "Table":

            caption = flush(before_table=True)
            buffer, buffer_chars, carried = [], 0, 0

            parts = _split_table_text(text, max_chars)

            for part_index, part in enumerate(parts):

                part_text = f"{caption}\n{part}" if caption and part_index == 0 else part
                table_element = dict(element, text=part_text)

                chunks.append(
                    _build_chunk_record(
                        [table_element],
                        section_heading,
                        len(chunks) + 1,
                        chunk_type="table",
                    )
                )
                chunk_elements.append([table_element])

            buffer_heading = section_heading
            previous_text = text
            continue

        if element.get("element_type") == "Title" and is_section_heading(
            text, allow_shape, previous_text
        ):

            section_heading = text

            # Only break here if what we already have is worth keeping;
            # otherwise the heading joins the chunk being built. Either way,
            # the label syncs immediately — otherwise a heading swallowed into
            # a not-yet-flushed buffer would leave that buffer (and everything
            # appended to it afterward) mislabelled with the heading in force
            # before this transition.
            if buffer_chars >= min_chars:
                flush()
            buffer_heading = section_heading

        if not buffer:
            buffer_heading = section_heading

        # Flush first if adding this element would blow past the hard ceiling
        # and there is already enough worth keeping. Without this, a carried
        # overlap tail plus one large element can combine to overshoot
        # max_chars well before the target_chars check below ever fires.
        if buffer and buffer_chars >= min_chars and buffer_chars + len(text) > max_chars:
            flush()
            if not buffer:
                buffer_heading = section_heading

        buffer.append(element)
        buffer_chars += len(text)
        previous_text = text

        if buffer_chars >= target_chars:
            flush()

    flush()

    for index, chunk in enumerate(chunks, start=1):
        chunk["chunk_id"] = f"CHUNK_{index:05}"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=4, ensure_ascii=False)

    print(f"Chunks created: {len(chunks)}")
    print("Saved successfully")

    return chunks


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


def _chunk_metadata(chunk, target_chars, overlap_chars):
    """Metadata stored alongside a chunk.

    source_file / page_number / section_heading / chunk_type are the locked
    Sprint 1 schema. page_start/page_end are additive — page_number is kept
    equal to page_start so nothing reading the locked schema breaks. The rest
    record which pipeline produced the vector, so stale embeddings can be
    spotted after a config change.
    """

    metadata = {
        "source_file": chunk["source_file"],
        "page_number": chunk["page_number"],
        "page_start": chunk.get("page_start", chunk["page_number"]),
        "page_end": chunk.get("page_end", chunk["page_number"]),
        "section_heading": chunk["section_heading"],
        "pipeline_version": PIPELINE_VERSION,
        "embedding_model": EMBEDDING_MODEL,
        "chunk_target_chars": target_chars,
        "chunk_overlap_chars": overlap_chars,
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
    target_chars=CHUNK_TARGET_CHARS,
    overlap_chars=CHUNK_OVERLAP_CHARS,
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
        _chunk_metadata(chunk, target_chars, overlap_chars)
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
