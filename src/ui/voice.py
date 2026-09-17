"""Voice input for the chat bar (Sprint 3, story 13).

The mic button, the live waveform and the recording itself are browser code in
voice.js, attached to Streamlit's chat bar through a built-in component. This
module takes what the browser sends back and decides what the user sees:

- a recording with speech in it is transcribed and put in the chat box, where the
  user checks it and sends it like anything typed. Nothing is answered from here.
- a recording with too little sound in it (silence, a sniff, a bump of the mic) is
  reported as nothing heard, without calling the backend.
- a failed transcription, or a mic the browser would not open, is reported as
  voice being unavailable. The chat box keeps working either way.
"""

import base64
import binascii
from pathlib import Path

import streamlit as st
from streamlit.components.v2 import component

from src.config import settings
from src.ui import responder

# Not "hs_voice": that key belongs to the hidden container app.py mounts this in,
# and Streamlit refuses two elements with the same key on one page.
COMPONENT_KEY = "hs_voice_bridge"

# The id of the last browser event handled. The browser sends a fresh id with
# every recording, so a value seen twice (Streamlit can replay a trigger into the
# rerun that handling it causes) is only ever acted on once.
HANDLED_KEY = "hs_voice_handled"
NOTICE_KEY = "hs_voice_notice"

HEARD = "heard"
NOTHING_HEARD = "nothing_heard"
FAILED = "failed"

_bridge = component(
    COMPONENT_KEY,
    js=Path(__file__).with_name("voice.js").read_text(encoding="utf-8"),
)


def _mount(slot):
    """Mount the bridge in `slot` and return (recording, unavailable) from the browser."""

    with slot:
        result = _bridge(
            key=COMPONENT_KEY,
            data={
                "max_seconds": settings.VOICE_MAX_SECONDS,
                "silence_level": settings.VOICE_SILENCE_LEVEL,
                "handled": st.session_state.get(HANDLED_KEY),
            },
            on_recording_change=lambda: None,
            on_unavailable_change=lambda: None,
        )

    return result.recording, result.unavailable


def _heard(recording):
    """Return (notice, transcript) for one recording."""

    try:
        voiced = float(recording.get("voiced") or 0)
        audio = base64.b64decode(recording.get("audio") or "", validate=True)
    except (TypeError, ValueError, binascii.Error):
        return FAILED, None

    # Brief noises are stopped here rather than sent: given a clip with no words in
    # it, the transcription model can invent a sentence instead of returning nothing.
    if not audio or voiced < settings.VOICE_MIN_SPEECH_SECONDS:
        return NOTHING_HEARD, None

    result = responder.transcribe(audio, recording.get("mime"))

    if result["status"] == "ok":
        return HEARD, result["text"]

    if result["status"] == "empty":
        return NOTHING_HEARD, None

    return FAILED, None


def take_recording(slot, question_key):
    """Handle anything the browser just sent, then redraw.

    Call before the chat input is drawn: the transcript is written into the input's
    session state, which Streamlit only allows before the widget exists in a run.
    """

    recording, unavailable = _mount(slot)
    event = recording or unavailable

    if not isinstance(event, dict) or event.get("id") is None:
        return

    if event["id"] == st.session_state.get(HANDLED_KEY):
        return

    if recording is not None:
        notice, transcript = _heard(recording)
    else:
        notice, transcript = FAILED, None

    if transcript:
        st.session_state[question_key] = transcript

    st.session_state[NOTICE_KEY] = notice
    st.session_state[HANDLED_KEY] = event["id"]

    # Start over so the browser receives the new handled id, which clears its
    # "Transcribing…" state, and so the input is drawn with the transcript in it.
    st.rerun()


def pop_notice():
    """The outcome of the last recording, shown once and then forgotten."""

    return st.session_state.pop(NOTICE_KEY, None)
