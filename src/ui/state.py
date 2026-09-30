"""Browser-session conversation state for the chat interface."""

import streamlit as st

CONVERSATIONS_KEY = "conversations"
ACTIVE_CONVERSATION_KEY = "active_conversation"
REQUEST_IN_FLIGHT_KEY = "request_in_flight"
NEXT_CONVERSATION_NUMBER_KEY = "next_conversation_number"
LABEL_LIMIT = 40

# Set once the tab's stored copy has been read back after a reload (browser_store).
RESTORED_KEY = "conversation_restored"

USER = "user"
ASSISTANT = "assistant"


def init_state():
    """Create one empty conversation on the first run of a browser session."""

    if CONVERSATIONS_KEY not in st.session_state:
        st.session_state[CONVERSATIONS_KEY] = {"conversation-1": []}
    if NEXT_CONVERSATION_NUMBER_KEY not in st.session_state:
        st.session_state[NEXT_CONVERSATION_NUMBER_KEY] = 2
    if ACTIVE_CONVERSATION_KEY not in st.session_state:
        st.session_state[ACTIVE_CONVERSATION_KEY] = next(iter(get_conversations()))
    if REQUEST_IN_FLIGHT_KEY not in st.session_state:
        st.session_state[REQUEST_IN_FLIGHT_KEY] = False


def get_conversations():
    """Return conversations in sidebar order, oldest first."""

    return st.session_state.get(CONVERSATIONS_KEY, {})


def active_conversation_id():
    """Return the selected conversation ID."""

    init_state()
    return st.session_state[ACTIVE_CONVERSATION_KEY]


def create_conversation():
    """Create and select a new empty conversation."""

    init_state()
    conversations = get_conversations()
    number = st.session_state[NEXT_CONVERSATION_NUMBER_KEY]
    conversation_id = f"conversation-{number}"
    st.session_state[NEXT_CONVERSATION_NUMBER_KEY] = number + 1
    conversations[conversation_id] = []
    st.session_state[ACTIVE_CONVERSATION_KEY] = conversation_id
    return conversation_id


def select_conversation(conversation_id):
    """Select an existing conversation without making a backend request."""

    init_state()
    if conversation_id not in get_conversations():
        raise KeyError(f"Unknown conversation: {conversation_id}")
    st.session_state[ACTIVE_CONVERSATION_KEY] = conversation_id


def delete_conversation(conversation_id):
    """Delete a conversation and select the most recent remaining one."""

    init_state()
    conversations = get_conversations()
    if conversation_id not in conversations:
        raise KeyError(f"Unknown conversation: {conversation_id}")

    del conversations[conversation_id]

    if not conversations:
        return create_conversation()

    if st.session_state[ACTIVE_CONVERSATION_KEY] == conversation_id:
        st.session_state[ACTIVE_CONVERSATION_KEY] = next(reversed(conversations))

    return st.session_state[ACTIVE_CONVERSATION_KEY]


def conversation_label(messages):
    """Return a sidebar label based on the first user question."""

    question = next(
        (message["content"].strip() for message in messages if message["role"] == USER),
        None,
    )
    if not question:
        return "New conversation"
    if len(question) <= LABEL_LIMIT:
        return question
    return question[: LABEL_LIMIT - 1].rstrip() + "…"


def get_messages():
    """The conversation so far, oldest first."""

    init_state()
    return get_conversations()[active_conversation_id()]


def add_message(role, content, *, sources=None, status=None):
    """Append one message and return it."""

    init_state()

    message = {"role": role, "content": content}

    if role == ASSISTANT:
        message["sources"] = sources or []
        message["status"] = status or "ok"

    get_messages().append(message)

    return message


def replace_messages(messages):
    """Swap the whole history, as when it is restored after a reload."""

    init_state()
    get_conversations()[active_conversation_id()] = list(messages)


def clear_messages():
    """Remove the active conversation's message history."""

    get_messages().clear()


def request_in_flight():
    """Whether the interface is currently waiting for a backend response."""

    return bool(st.session_state.get(REQUEST_IN_FLIGHT_KEY, False))


def set_request_in_flight(value):
    """Set the request guard used to prevent duplicate submissions."""

    st.session_state[REQUEST_IN_FLIGHT_KEY] = value
