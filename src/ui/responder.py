"""Where the interface gets its answers from.

PLACEHOLDER. This is the one seam between the chat interface and whatever
actually answers a question, and it is meant to be replaced:

    phase 1 (here)  a canned stub, so the layout can be built with no backend
    phase 3         a plain gpt-5-mini call, so the prototype can be talked to
    story 4         an HTTP call to the FastAPI /chat endpoint, RAG and all

app.py only ever calls stream_reply(). Swapping the body of this function is the
whole of that change — nothing in the interface needs to move.
"""

import time

# Typing speed for the stub, in seconds per word. Slow enough to read as a reply
# being written rather than a block of text appearing at once.
STUB_WORD_DELAY = 0.02

STUB_REPLY = (
    "This is a placeholder reply so the layout can be reviewed before the "
    "backend is connected. Once the retrieval pipeline is wired in, an answer "
    "here will be drawn from the WorkSafe guidance in the corpus and shown "
    "with the document and page it came from."
)


def stream_reply(question, history=None):
    """Yield an answer to `question` in chunks, oldest history first.

    A generator rather than a plain string so st.write_stream can render the
    reply as it arrives. The real model streams too, so the call site does not
    change when this stub goes away.
    """

    for word in STUB_REPLY.split(" "):
        time.sleep(STUB_WORD_DELAY)
        yield word + " "
