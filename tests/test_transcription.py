"""Tests for turning a recorded question into text (Sprint 3, story 13).

The OpenAI client is a stub that records what it was asked, so nothing here calls
the API.
"""

from types import SimpleNamespace

import pytest

from src.config import settings
from src.config.prompts import TRANSCRIPTION_PROMPT
from src.transcription import transcribe

AUDIO = b"fake webm bytes"


class StubClient:
    """Stands in for OpenAI(): client.audio.transcriptions.create(...)."""

    def __init__(self, text="Do I need edge protection on a roof?"):
        self.calls = []
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))
        self._text = text

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self._text)


def test_the_transcript_comes_back_as_ok():
    result = transcribe(AUDIO, "question.webm", StubClient())

    assert result == {"text": "Do I need edge protection on a roof?", "status": "ok"}


def test_the_configured_model_language_and_vocabulary_prompt_are_used():
    client = StubClient()

    transcribe(AUDIO, "question.webm", client)

    call = client.calls[0]
    assert call["model"] == settings.TRANSCRIPTION_MODEL
    assert call["language"] == settings.TRANSCRIPTION_LANGUAGE
    assert call["prompt"] == TRANSCRIPTION_PROMPT
    assert call["chunking_strategy"] == settings.TRANSCRIPTION_CHUNKING_STRATEGY
    # The API reads the format from the filename, so it must travel with the bytes.
    assert call["file"] == ("question.webm", AUDIO)


def test_surrounding_whitespace_is_stripped():
    result = transcribe(AUDIO, "question.webm", StubClient("  Who is a PCBU?\n"))

    assert result["text"] == "Who is a PCBU?"


@pytest.mark.parametrize("text", ["", "   ", None])
def test_a_blank_transcript_means_nothing_was_heard(text):
    result = transcribe(AUDIO, "question.webm", StubClient(text))

    assert result == {"text": "", "status": "empty"}


@pytest.mark.parametrize("filename", ["question.webm", "question.ogg", "question.mp4", "QUESTION.WAV"])
def test_browser_recording_formats_are_accepted(filename):
    assert transcribe(AUDIO, filename, StubClient())["status"] == "ok"


def test_an_empty_recording_is_refused_without_calling_the_api():
    client = StubClient()

    with pytest.raises(ValueError):
        transcribe(b"", "question.webm", client)

    assert client.calls == []


@pytest.mark.parametrize("filename", ["question.txt", "question", None])
def test_an_unsupported_format_is_refused_without_calling_the_api(filename):
    client = StubClient()

    with pytest.raises(ValueError):
        transcribe(AUDIO, filename, client)

    assert client.calls == []


def test_the_vocabulary_prompt_gives_the_model_nothing_to_complete():
    """A topic or a question in the prompt is what a sniff was once transcribed into."""

    assert "?" not in TRANSCRIPTION_PROMPT
    assert "question" not in TRANSCRIPTION_PROMPT.lower()
