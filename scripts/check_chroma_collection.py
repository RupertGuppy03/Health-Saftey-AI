"""Script to quickly open the persisted ChromaDB collection and print the count.

Usage:
    python scripts/check_chroma_collection.py [--collection NAME]

If run in a developer environment after pip installing requirements, this should
open the persisted collection under ./vectorstore/ and print how many items it
contains. This works without running any ingestion step; if the collection
doesn't exist yet it will be created (empty).
"""

import argparse
import sys
from pathlib import Path

# Run directly (python scripts/check_chroma_collection.py) and only this folder
# is on sys.path, so `src` would not resolve. Put the repo root on the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.vectorstore_client import get_collection, count_collection


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--collection", help="Collection name to open (overrides config)", default=None)
    args = p.parse_args(argv)

    collection_name = args.collection
    try:
        col = get_collection(collection_name)
        cnt = count_collection(collection_name)
        print(f"Opened collection: {col.name if hasattr(col, 'name') else collection_name}")
        print(f"Approximate item count: {cnt}")
        return 0
    except Exception as e:
        print("Failed to open ChromaDB collection:", str(e))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
