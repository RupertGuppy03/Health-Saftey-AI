#!/usr/bin/env bash
# Run the Streamlit chat interface (development helper). Uses python3 where available.
# The backend does not need to be running: the interface answers from a stub.

set -euo pipefail

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "No python3 or python binary found. Please install Python 3.10+ and ensure 'python3' is on PATH." >&2
  exit 1
fi

# Default port. Streamlit's own default is 8501.
PORT=${PORT:-8501}

# Run from the repo root so the app can import from src/.
cd "$(dirname "$0")/.."

echo "Starting the chat interface on port ${PORT}"
$PY -m streamlit run streamlit_app.py --server.port "$PORT"
