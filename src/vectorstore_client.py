"""Small helper for opening a persisted ChromaDB client and named collection.

Consumers should import get_collection or count_collection and not hardcode
collection names or paths.
"""

from typing import Optional
from pathlib import Path

import chromadb

from src.config.settings import CHROMA_COLLECTION_NAME, CHROMA_PERSIST_DIR


def _ensure_persist_dir_exists() -> Path:
    path = Path(CHROMA_PERSIST_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_client() -> chromadb.Client:  # type: ignore
    """Return a persistent Chroma client that writes to CHROMA_PERSIST_DIR.

    Uses chromadb.PersistentClient when available, falling back to the Client +
    Settings API for versions where that is preferred.
    """
    persist_path = str(_ensure_persist_dir_exists())
    try:
        # Newer/chosen API: PersistentClient
        client = chromadb.PersistentClient(path=persist_path)
        return client
    except Exception:
        # Fallback: construct a Client with settings specifying persist_directory.
        try:
            from chromadb.config import Settings

            settings = Settings(
                chroma_db_impl="duckdb+parquet", persist_directory=persist_path
            )
            client = chromadb.Client(settings=settings)
            return client
        except Exception:
            # As a final fallback, try a default Client (in-memory) — but this will not persist.
            return chromadb.Client()


def get_collection(name: Optional[str] = None):
    """Get or create the named collection using the persistent client.

    Returns the chroma collection object.
    """
    client = get_client()
    name = name or CHROMA_COLLECTION_NAME
    return client.get_or_create_collection(name=name)


def count_collection(name: Optional[str] = None) -> int:
    """Return an approximate count of items (documents/embeddings) in the collection.

    Uses collection.count() when available; falls back to len of ids if necessary.
    """
    col = get_collection(name)
    try:
        return int(col.count())
    except Exception:
        # Try to get document IDs and count them (may be heavier)
        try:
            ids = col.get(ids=True)
            if isinstance(ids, dict) and "ids" in ids:
                return len(ids["ids"])  # depending on API
            return len(ids)
        except Exception:
            return 0
