"""Central project settings.

Paths and constants the rest of the code reads from one place instead of
hard-coding them. Everything is anchored to the repo root so it works no
matter where a script or test is run from.
"""

from pathlib import Path

# Repo root: this file is at <root>/src/config/settings.py, so go up three levels.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Data folders.
DATA_DIR = PROJECT_ROOT / "data"
DATA_RAW_DIR = DATA_DIR / "raw"
DATA_PROCESSED_DIR = DATA_DIR / "processed"

# Sample document used for the Sprint 1 extraction spike / demo.
# The smallest construction guide — a good single-document test case before
# running the pipeline across the whole corpus.
SAMPLE_PDF = (
    DATA_RAW_DIR
    / "building_and_construction"
    / "pcbus_working_together"
    / "PCBUs-Working-Together-GPG.pdf"
)

# ChromaDB / vectorstore configuration
# Single source-of-truth: collection name and where to persist the DB on disk.
# Change CHROMA_COLLECTION_NAME here if a new version is created (e.g. hs_construction_v2).
CHROMA_COLLECTION_NAME = "hs_construction_v1"
CHROMA_PERSIST_DIR = PROJECT_ROOT / "vectorstore"

# OpenAI embedding configuration
# Single source-of-truth for the embedding model used at BOTH ingestion and query
# time. Retrieval must embed the user's question with this same model, otherwise
# the vectors are not comparable.
EMBEDDING_MODEL = "text-embedding-3-small"

# The model's native output size. Do NOT pass dimensions= to the API to truncate:
# the collection is built at this width and a mismatch is a hard error.
EMBEDDING_DIMENSIONS = 1536

# How many texts to send per embeddings API call. Batching keeps the request count
# (and the per-request overhead) down: the full corpus is ~5,400 chunks, which is
# ~43 calls at this size instead of ~5,400.
EMBEDDING_BATCH_SIZE = 128

# Safety cap well below the API's per-request token limit. A batch that would
# exceed this is split again, so a handful of unusually long chunks cannot push a
# request over the edge.
EMBEDDING_MAX_TOKENS_PER_REQUEST = 100_000

# Pipeline provenance
# Stamped onto every stored record so stale embeddings are detectable after a
# pipeline change. Bump this when chunking, cleaning or the embedding model
# changes in a way that invalidates vectors already in the collection.
PIPELINE_VERSION = "3.0.0"

# Chunking configuration.
# Chunks are built by packing whole elements in document order rather than by
# splitting a joined string, so these are targets for the packer rather than
# arguments to a text splitter.
CHUNK_TARGET_CHARS = 3000    # aim for this; ~750 tokens, inside the locked 500-1000 band
CHUNK_MAX_CHARS = 4000       # hard ceiling for any single chunk
CHUNK_MIN_CHARS = 300        # never emit a chunk smaller than this; merge it backwards
CHUNK_OVERLAP_CHARS = 600    # trailing context carried into the next prose chunk

# A document whose Title elements are at least this structural (numbered, or short
# ALL CAPS) is treated as having a clear heading convention, and only those count
# as section breaks. Below it, the looser shape rule is enabled as well.
HEADING_STRUCTURAL_SHARE = 0.40
