"""Keeps a copy of the conversations in the browser tab so they survive a reload.

st.session_state belongs to the websocket connection, and a reload opens a new
one, so on its own the history is gone the moment the page is refreshed. This
module mirrors every conversation, and which one is open, into the tab's
sessionStorage and reads them back once at the start of each new session.

sessionStorage is per tab and cleared when the tab closes, so the conversation
is still scoped to one browser session and nothing is kept on the server.

The browser answers asynchronously: on the first run of a reloaded session the
stored copy has not arrived yet, so restore() reports it is still waiting and
the page draws nothing until the component sends it back and Streamlit reruns.
"""

import json

import streamlit as st
from streamlit.components.v2 import component

from src.ui import state

COMPONENT_KEY = "hs_conversation_store"

LOAD = "load"
SAVE = "save"

# Load sends the stored copy back (or "{}" for a fresh tab), which reruns the
# script. Save writes the current conversations over it. A storage error on load
# still answers "{}" so the page is never left waiting.
JS = """
const KEY = "hs_conversation";

export default function ({ data, setTriggerValue }) {
    if (!data) return;

    if (data.mode === "save") {
        try { sessionStorage.setItem(KEY, data.messages); } catch (e) {}
        return;
    }

    let raw = null;
    try { raw = sessionStorage.getItem(KEY); } catch (e) {}
    setTriggerValue("loaded", raw ?? "{}");
}
"""

_bridge = component(COMPONENT_KEY, js=JS)


def _mount(slot, mode, messages=None):
    """Mount the bridge in `slot` and return the stored copy if it just arrived."""

    with slot:
        result = _bridge(
            key=COMPONENT_KEY,
            data={"mode": mode, "messages": messages},
            on_loaded_change=lambda: None,
        )

    return result.loaded


def _valid_store(raw):
    """Parse the stored copy into (conversations, active ID), keeping only well-formed messages."""

    try:
        stored = json.loads(raw)
    except (TypeError, ValueError):
        return {}, None

    # A tab saved before there were several conversations holds one bare list.
    if isinstance(stored, list):
        stored = {"conversations": {"conversation-1": stored}}

    if not isinstance(stored, dict) or not isinstance(stored.get("conversations"), dict):
        return {}, None

    conversations = {
        conversation_id: _valid_messages(messages)
        for conversation_id, messages in stored["conversations"].items()
    }

    return conversations, stored.get("active")


def _valid_messages(stored):
    """Keep only the well-formed messages of one stored conversation."""

    if not isinstance(stored, list):
        return []

    messages = []

    for message in stored:
        if not isinstance(message, dict):
            continue

        if message.get("role") not in (state.USER, state.ASSISTANT):
            continue

        if not isinstance(message.get("content"), str):
            continue

        messages.append(message)

    return messages


def restore(slot):
    """True once this session holds the tab's conversation, False while waiting.

    When the stored copy arrives it is loaded and the script reruns, so a True
    only ever comes back from a run that did not mount the bridge.
    """

    if st.session_state.get(state.RESTORED_KEY):
        return True

    raw = _mount(slot, LOAD)

    if raw is None:
        return False

    state.restore_conversations(*_valid_store(raw))
    st.session_state[state.RESTORED_KEY] = True

    # Start over rather than carry on, so the bridge is mounted only once per run
    # (the save at the end of this run would reuse its key).
    st.rerun()


def save(slot, snapshot):
    """Write the current conversations over the tab's copy."""

    _mount(slot, SAVE, json.dumps(snapshot))
