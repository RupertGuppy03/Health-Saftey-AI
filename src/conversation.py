"""Shaping the conversation history that travels with a question.

Pure functions with no I/O and no module-level state. That is the point rather
than a style choice: a conversation belongs to one browser session, so there is
deliberately nowhere here for one user's messages to be stored, cached or keyed.
History arrives as an argument, is reshaped, and is handed straight back.

Both sides of the app use this. The interface trims before it posts, to keep the
request small; the backend trims again on arrival, because it cannot trust what
it was sent. They agree because they read the same limit from src.config.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

import tiktoken

from src.config.settings import HISTORY_TOKEN_LIMIT

USER = "user"
ASSISTANT = "assistant"

ROLES = (USER, ASSISTANT)

# The same encoding the ingestion pipeline counts chunks with, so a "token" means
# the same thing at both ends of the project.
ENCODING_NAME = "cl100k_base"


@lru_cache(maxsize=1)
def _encoding():
    """The tokeniser, built once. Holds no conversation data — only the model."""

    return tiktoken.get_encoding(ENCODING_NAME)


def count_tokens(text: str) -> int:
    """How many tokens a piece of text costs to send."""

    if not text:
        return 0

    return len(_encoding().encode(text))


def normalise(history: Optional[Iterable[Any]]) -> List[Dict[str, str]]:
    """Keep the well-formed turns and quietly drop everything else.

    The interface stores more on a message than a turn needs — sources, a status,
    whatever a later story adds — and an assistant message can be empty if a reply
    failed. Only the role and the text travel, so nothing incidental to how the UI
    draws a bubble ends up in a prompt.
    """

    turns: List[Dict[str, str]] = []

    for message in history or []:
        if not isinstance(message, dict):
            continue

        role = message.get("role")
        content = message.get("content")

        if role not in ROLES or not isinstance(content, str) or not content.strip():
            continue

        turns.append({"role": role, "content": content})

    return turns


def trim(history: Optional[Iterable[Any]], token_limit: Optional[int] = None) -> List[Dict[str, str]]:
    """The most recent turns that fit the budget, oldest first.

    Walks backwards from the newest turn and stops as soon as the next one would
    not fit, so the work is bounded by the limit rather than by the length of the
    conversation it was handed.

    A history that starts on an assistant turn is an answer whose question was
    just trimmed away, which reads as the assistant having spoken first. The
    leading turn is dropped so history always begins with something the user said.
    """

    if token_limit is None:
        token_limit = HISTORY_TOKEN_LIMIT

    turns = normalise(history)

    if token_limit <= 0:
        return []

    kept: List[Dict[str, str]] = []
    spent = 0

    for turn in reversed(turns):
        cost = count_tokens(turn["content"])

        if spent + cost > token_limit:
            break

        kept.append(turn)
        spent += cost

    kept.reverse()

    while kept and kept[0]["role"] != USER:
        kept.pop(0)

    return kept


def as_messages(history: Optional[Iterable[Any]]) -> List[Tuple[str, str]]:
    """(role, content) pairs for the prompt's MessagesPlaceholder.

    Sent as real user and assistant messages rather than pasted into one block of
    text, so the model can tell what someone typed from what it is being told to
    do. An earlier turn cannot pose as an instruction if it never shares a message
    with one.
    """

    return [(turn["role"], turn["content"]) for turn in normalise(history)]


def as_transcript(history: Optional[Iterable[Any]]) -> str:
    """The conversation as plain text, for the rewrite prompt to read."""

    labels = {USER: "User", ASSISTANT: "Assistant"}

    return "\n".join(
        f"{labels[turn['role']]}: {turn['content']}" for turn in normalise(history)
    )
