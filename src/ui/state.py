"""Conversation state for the chat interface.

Streamlit re-runs the whole script on every interaction, so the message history
has to live in st.session_state rather than in a module-level list. Nothing here
knows about the pipeline — a message is just a role and some text.
"""

import streamlit as st

MESSAGES_KEY = "messages"
REQUEST_IN_FLIGHT_KEY = "request_in_flight"

# Set once the tab's stored copy has been read back after a reload (browser_store).
RESTORED_KEY = "conversation_restored"

USER = "user"
ASSISTANT = "assistant"


def init_state():
    """Create an empty history on the first run of a browser session."""

    if MESSAGES_KEY not in st.session_state:
        st.session_state[MESSAGES_KEY] = []
    if REQUEST_IN_FLIGHT_KEY not in st.session_state:
        st.session_state[REQUEST_IN_FLIGHT_KEY] = False


def get_messages():
    """The conversation so far, oldest first."""

    return st.session_state.get(MESSAGES_KEY, [])


def add_message(role, content, *, sources=None, status=None):
    """Append one message and return it."""

    init_state()

    message = {"role": role, "content": content}

    if role == ASSISTANT:
        message["sources"] = sources or []
        message["status"] = status or "ok"

    st.session_state[MESSAGES_KEY].append(message)

    return message


def replace_messages(messages):
    """Swap the whole history, as when it is restored after a reload."""

    st.session_state[MESSAGES_KEY] = list(messages)


def clear_messages():
    """Remove the conversation history for this browser session."""

    st.session_state[MESSAGES_KEY] = []


def request_in_flight():
    """Whether the interface is currently waiting for a backend response."""

    return bool(st.session_state.get(REQUEST_IN_FLIGHT_KEY, False))


def set_request_in_flight(value):
    """Set the request guard used to prevent duplicate submissions."""

    st.session_state[REQUEST_IN_FLIGHT_KEY] = value

