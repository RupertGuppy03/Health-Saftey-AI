#!/usr/bin/env bash
# Run the FastAPI app (development helper). Uses python3 where available.

set -euo pipefail

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "No python3 or python binary found. Please install Python 3.10+ and ensure 'python3' is on PATH." >&2
  exit 1
fi

# Default host/port
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}

echo "Starting FastAPI app on ${HOST}:${PORT}"
$PY -m uvicorn src.api.app:app --host "$HOST" --port "$PORT" --reload
