"""Conversation state for the chat interface.

Streamlit re-runs the whole script on every interaction, so the message history
has to live in st.session_state rather than in a module-level list. Nothing here
knows about the pipeline — a message is just a role and some text.
"""

import streamlit as st

MESSAGES_KEY = "messages"

USER = "user"
ASSISTANT = "assistant"


def init_state():
    """Create an empty history on the first run of a browser session."""

    if MESSAGES_KEY not in st.session_state:
        st.session_state[MESSAGES_KEY] = []


def get_messages():
    """The conversation so far, oldest first."""

    return st.session_state.get(MESSAGES_KEY, [])


def add_message(role, content):
    """Append one message and return it."""

    init_state()

    message = {"role": role, "content": content}
    st.session_state[MESSAGES_KEY].append(message)

    return message
