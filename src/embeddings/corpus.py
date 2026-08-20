"""Corpus overview for the Sprint 2 ingestion notebook.

Answers the two questions asked before anything is chunked or embedded: which
cleaned documents exist under data/processed/, and which of them are already in
the vector store. Nothing here calls OpenAI or writes to the collection.
"""

import json
from pathlib import Path

from src.config.settings import DATA_PROCESSED_DIR
from src.vectorstore_client import get_collection

CLEANED_SUFFIX = "-CLEANED.json"


def _chunks_path(cleaned_json):
    """The chunk file that sits alongside a cleaned file (-CLEANED -> -CHUNKS)."""

    return cleaned_json.with_name(cleaned_json.name.replace("-CLEANED", "-CHUNKS"))


def _source_file(cleaned_json):
    """The PDF filename recorded inside a cleaned file.

    The folder slug is not the source_file — the vector store keys on the PDF
    name, so read it from the data rather than deriving it from the path. An
    empty or unreadable file yields "" instead of raising, so one bad document
    cannot take out the whole status table.
    """

    try:
        records = json.loads(cleaned_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    for record in records:
        source = record.get("source_file", "")
        if source:
            return source

    return ""


def _count_chunks_on_disk(chunks_json):
    """How many chunk records the derived *-CHUNKS.json holds, 0 if absent."""

    if not chunks_json.exists():
        return 0

    try:
        return len(json.loads(chunks_json.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return 0


def list_cleaned_documents(processed_dir=DATA_PROCESSED_DIR):
    """One entry per document folder holding a *-CLEANED.json, sorted by name.

    Each entry: name, cleaned_json, chunks_json, source_file. Folders without a
    cleaned file are skipped, so README.md and any stray directory drop out.
    """

    documents = []

    for folder in sorted(Path(processed_dir).iterdir()):

        if not folder.is_dir():
            continue

        cleaned = sorted(folder.glob(f"*{CLEANED_SUFFIX}"))

        if not cleaned:
            continue

        documents.append(
            {
                "name": folder.name,
                "cleaned_json": cleaned[0],
                "chunks_json": _chunks_path(cleaned[0]),
                "source_file": _source_file(cleaned[0]),
            }
        )

    return documents


def ingested_chunk_counts(collection_name=None):
    """source_file -> number of records currently held in the collection."""

    collection = get_collection(collection_name)
    metadatas = collection.get(include=["metadatas"])["metadatas"] or []

    counts = {}

    for metadata in metadatas:
        source = (metadata or {}).get("source_file")

        if source:
            counts[source] = counts.get(source, 0) + 1

    return counts


def corpus_status(processed_dir=DATA_PROCESSED_DIR, collection_name=None):
    """Every cleaned document with its chunk counts on disk and in the store.

    Extends each list_cleaned_documents entry with chunks_on_disk and
    chunks_in_store. This is what tells you which document to run next.
    """

    counts = ingested_chunk_counts(collection_name)
    status = []

    for document in list_cleaned_documents(processed_dir):

        entry = dict(document)
        entry["chunks_on_disk"] = _count_chunks_on_disk(document["chunks_json"])
        entry["chunks_in_store"] = counts.get(document["source_file"], 0)

        status.append(entry)

    return status


def format_status_table(status):
    """Render corpus_status() as a plain text table for the notebook."""

    name_width = max([len(entry["name"]) for entry in status] + [8])

    header = f"  {'document'.ljust(name_width)}  {'on disk':>8}  {'in store':>9}"
    lines = [header, "  " + "-" * (name_width + 21)]

    for entry in status:
        on_disk = entry["chunks_on_disk"] or "-"
        in_store = entry["chunks_in_store"] or "-"
        lines.append(
            f"  {entry['name'].ljust(name_width)}  {str(on_disk):>8}  {str(in_store):>9}"
        )

    stored = sum(1 for entry in status if entry["chunks_in_store"])
    lines.append("")
    lines.append(f"  {stored} of {len(status)} documents in the collection")

    return "\n".join(lines)
