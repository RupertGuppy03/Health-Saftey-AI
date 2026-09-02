"""Acceptance test 4: the interface holds no pipeline code.

Parses every module the interface is made of and looks at what it imports. This
is a static check on purpose — importing the modules to inspect them would prove
nothing, because an import that only happens inside a function would slip past.

The rule matters because the interface is meant to be swappable and deployable
on its own: story 4 replaces the placeholder in responder.py with an HTTP call
to the backend, and the backend stays the only component that holds the vector
store, the model clients and the API key. Answers today come from a stub, so the
interface has no reason to reach for any of this.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_DIR = REPO_ROOT / "src" / "ui"
ENTRYPOINT = REPO_ROOT / "streamlit_app.py"

# Nothing in the interface may import these, at module level or anywhere else.
FORBIDDEN = (
    "chromadb",
    "langchain",
    "openai",
    "src.answer",
    "src.retrieval",
    "src.embeddings",
    "src.vectorstore_client",
)


def _interface_modules():
    return sorted(UI_DIR.glob("*.py")) + [ENTRYPOINT]


def _imported_names(path):
    """Every module name the file imports, dotted and in full."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = []

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)

        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
            names.extend(f"{node.module}.{alias.name}" for alias in node.names)

    return names


def _is_forbidden(name):
    return any(name == banned or name.startswith(banned + ".") for banned in FORBIDDEN)


# =====================================================
# THE CHECK HAS SOMETHING TO CHECK
# =====================================================

def test_the_interface_modules_are_found():
    # Guards against the test passing because it scanned nothing.
    modules = _interface_modules()

    assert len(modules) >= 4
    assert (UI_DIR / "app.py") in modules


# =====================================================
# NO PIPELINE CODE IN THE INTERFACE
# =====================================================

@pytest.mark.parametrize("path", _interface_modules(), ids=lambda p: p.name)
def test_no_pipeline_code_is_imported(path):
    offenders = [name for name in _imported_names(path) if _is_forbidden(name)]

    assert offenders == []


def test_the_interface_may_still_read_project_settings():
    # src.config holds plain paths and constants and pulls in nothing heavy, so
    # it is the one project module the interface is allowed to depend on.
    from src.ui import corpus

    assert corpus.DATA_RAW_DIR.name == "raw"
