#!/usr/bin/env bash
# Small helper to run quick sanity checks using python3 so macOS/Linux users
# without a 'python' shim don't see `python: command not found`.

set -euo pipefail

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "No python3 or python binary found. Please install Python 3.10+ and ensure 'python3' is on PATH." >&2
  exit 1
fi

echo "Running a quick module import / smoke-check using $PY"
$PY - <<'PY'
try:
    import importlib
    importlib.import_module('src.answer')
    importlib.import_module('src.retrieval.retriever')
    print('Import checks passed')
except Exception as e:
    print('Import check failed:', e)
    raise
PY

echo "Done. To run tests use: $PY -m pytest -q"
