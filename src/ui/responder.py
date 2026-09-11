"""Where the interface gets its answers from.

The one seam between the chat interface and the pipeline. It reaches the RAG
backend over HTTP rather than importing it, which is what keeps ChromaDB,
LangChain and the OpenAI credentials out of the interface process entirely —
the backend is the only component that holds them.

app.py only ever calls stream_reply().
"""

import time

import httpx

from src.config import settings

# Pause between words when replaying an answer, in seconds. The backend returns
# a finished answer rather than a stream, so this replays it at reading speed
# instead of dropping the whole block in at once.
WORD_DELAY = 0.02

# Shown when the backend cannot be reached or fails. Deliberately plain: story 8
# owns real error handling, the readiness check and the loading indicator, and
# replaces this with messages that distinguish the failures from each other.
FALLBACK_REPLY = (
    "I could not reach the answering service, so I cannot answer that right "
    "now. Check that the backend is running, then try again."
)


def stream_reply(question, history=None):
    """Yield an answer to `question` in chunks, oldest history first.

    A generator rather than a plain string so st.write_stream can render the
    reply as it arrives.

    `history` is accepted but unused — the backend answers each question on its
    own, and sending the conversation with it is story 10.
    """

    try:
        response = httpx.post(
            f"{settings.API_BASE_URL}/chat",
            json={"question": question},
            timeout=settings.API_TIMEOUT_SECONDS,
        )
    except httpx.RequestError:
        yield FALLBACK_REPLY
        return

    # A 200 carries a user-facing answer whether the pipeline answered it, found
    # nothing, or refused it as out of scope, so all three render the same way.
    # Anything else is a validation or server error whose message is written for
    # a developer, not for whoever is asking the question.
    if response.status_code != 200:
        yield FALLBACK_REPLY
        return

    answer = response.json().get("answer", "")

    for word in answer.split(" "):
        time.sleep(WORD_DELAY)
        yield word + " "
