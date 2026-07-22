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
