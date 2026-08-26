"""Embed every chunked document in the corpus into the vector store, in one run.

The vector store is gitignored, so it never arrives with a merge — only the
`*-CHUNKS.json` files do. Anyone pulling a branch has the chunks but an empty or
partial collection, and the Sprint 2 notebook only embeds one document per run
via `DOC_DIR`. This script closes that gap: it walks `data/processed/` and
ingests every document that has a chunk file.

Safe to re-run. `ingest_to_chromadb()` builds deterministic chunk IDs and
upserts, so a repeat run overwrites the same records instead of appending, and
prunes any record the current chunking no longer produces.

The embedding calls are paid. The whole corpus is roughly 3,600 chunks — about
1.2M tokens, a few cents. Needs OPEN_AI_API_KEY (or OPENAI_API_KEY) in .env.

Usage:
    python -m src.ingestion.backfill_vectorstore
"""

from __future__ import annotations

import argparse
import sys

from src.embeddings import corpus
from src.embeddings.chunking_script_v2 import ingest_to_chromadb


def backfill(collection_name=None):
    """Ingest every document under data/processed/ that has a chunk file.

    Returns (ingested, skipped, failed) — lists of document names. A document
    that raises is reported and the run carries on to the rest: a single bad
    file should not abandon a paid run partway through, leaving the collection
    in a state nobody can reason about.
    """

    documents = corpus.list_cleaned_documents()

    ingested, skipped, failed = [], [], []
    running_total = 0

    print(f"Found {len(documents)} cleaned document(s) under data/processed/\n")

    for position, document in enumerate(documents, start=1):
        name = document["name"]
        chunks_json = document["chunks_json"]

        if not chunks_json.exists():
            print(f"[{position}/{len(documents)}] {name}\n    skipped — no *-CHUNKS.json\n")
            skipped.append(name)
            continue

        print(f"[{position}/{len(documents)}] {name}")

        try:
            summary = ingest_to_chromadb(chunks_json, collection_name=collection_name)
        except Exception as error:
            # Keep going. The failure is re-reported in the final summary so it
            # cannot get lost in the scrollback of a 20-document run.
            print(f"    FAILED — {type(error).__name__}: {error}\n")
            failed.append(name)
            continue

        running_total += summary["chunks_embedded"]
        ingested.append(name)

        print(f"    running total: {running_total} chunks\n")

    return ingested, skipped, failed


def main():
    parser = argparse.ArgumentParser(
        description="Embed every chunked document into the ChromaDB collection."
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Collection name to write to (defaults to CHROMA_COLLECTION_NAME)",
    )
    args = parser.parse_args()

    ingested, skipped, failed = backfill(args.collection)

    print("=" * 78)
    print(corpus.format_status_table(corpus.corpus_status(collection_name=args.collection)))
    print()
    print(f"  ingested : {len(ingested)}")

    if skipped:
        print(f"  skipped  : {len(skipped)} — {', '.join(skipped)}")

    if failed:
        print(f"  FAILED   : {len(failed)} — {', '.join(failed)}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
