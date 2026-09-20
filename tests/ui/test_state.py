"""Unit tests for browser-session conversation state."""

import pytest

from src.ui import state


@pytest.fixture
def session_state(monkeypatch):
    values = {}
    monkeypatch.setattr(state.st, "session_state", values)
    return values


def test_initial_state_contains_one_empty_conversation(session_state):
    state.init_state()

    assert len(state.get_conversations()) == 1
    assert state.get_messages() == []


def test_new_conversation_keeps_the_previous_messages(session_state):
    state.init_state()
    state.add_message(state.USER, "First question")
    first_id = state.active_conversation_id()

    second_id = state.create_conversation()

    assert second_id != first_id
    assert state.get_messages() == []
    state.select_conversation(first_id)
    assert [message["content"] for message in state.get_messages()] == ["First question"]


def test_replacing_messages_updates_the_active_conversation(session_state):
    state.init_state()

    messages = [{"role": state.USER, "content": "Restored question"}]
    state.replace_messages(messages)

    assert state.get_messages() == messages


def test_label_uses_and_truncates_the_first_user_question():
    question = "A" * 50

    assert state.conversation_label([
        {"role": state.USER, "content": question},
        {"role": state.ASSISTANT, "content": "answer"},
    ]) == ("A" * 39) + "…"


def test_empty_conversation_has_a_generic_label():
    assert state.conversation_label([]) == "New conversation"


def test_deleting_active_conversation_selects_the_most_recent_remaining(session_state):
    state.init_state()
    middle_id = state.create_conversation()
    second_id = state.create_conversation()

    state.delete_conversation(state.active_conversation_id())

    assert state.active_conversation_id() == middle_id
    assert second_id not in state.get_conversations()


def test_deleting_the_last_conversation_creates_an_empty_one(session_state):
    state.init_state()
    only_id = state.active_conversation_id()
    state.add_message(state.USER, "Question")

    new_id = state.delete_conversation(only_id)

    assert new_id != only_id
    assert state.get_messages() == []


def test_selecting_an_unknown_conversation_is_explicit(session_state):
    state.init_state()

    with pytest.raises(KeyError):
        state.select_conversation("missing")
