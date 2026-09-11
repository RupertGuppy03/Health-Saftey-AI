"""Tests for the interface's call to the FastAPI backend.

Nothing here starts a server or makes a real request: httpx.post is replaced in
the responder's own namespace, so every test asserts on what the interface sent
and what it did with the reply. The word delay is patched to zero throughout,
otherwise a multi-word answer would sleep its way through the suite.
"""

import httpx
import pytest

from src.config import settings
from src.ui import responder


# =====================================================
# FIXTURES
# =====================================================

ANSWER = "Edge protection is required on any roof where a fall is possible."


@pytest.fixture(autouse=True)
def no_word_delay(monkeypatch):
    """Replay answers instantly; the pacing is cosmetic and not under test."""

    monkeypatch.setattr(responder, "WORD_DELAY", 0)


def _response(payload, status_code=200):
    """A real httpx.Response, so status_code and .json() behave as they do live."""

    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("POST", "http://testserver/chat"),
    )


def _capture(monkeypatch, response):
    """Swap httpx.post for a recorder, and hand back the calls it collects."""

    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(responder.httpx, "post", fake_post)

    return calls


def _reply(question="What edge protection do I need for work at height?"):
    """The full answer as the user would see it, with the streaming rejoined."""

    return "".join(responder.stream_reply(question)).strip()


# =====================================================
# THE ANSWER COMES FROM THE BACKEND
# =====================================================

def test_the_answer_shown_is_the_answer_the_backend_returned(monkeypatch):
    _capture(monkeypatch, _response({"answer": ANSWER, "sources": [],
                                     "latency_seconds": 3.2, "status": "ok"}))

    assert _reply() == ANSWER


def test_the_placeholder_reply_is_gone():
    """The stub sentence must not survive anywhere in the module."""

    assert not hasattr(responder, "STUB_REPLY")


def test_the_question_is_posted_to_the_chat_endpoint(monkeypatch):
    calls = _capture(monkeypatch, _response({"answer": ANSWER, "sources": [],
                                             "latency_seconds": 3.2, "status": "ok"}))

    _reply("Do I need a harness on a scaffold?")

    assert len(calls) == 1
    assert calls[0]["url"] == f"{settings.API_BASE_URL}/chat"
    assert calls[0]["json"] == {"question": "Do I need a harness on a scaffold?"}


def test_the_request_waits_longer_than_the_httpx_default(monkeypatch):
    """A real answer takes ~33s, so the 5 second default would fail every call."""

    calls = _capture(monkeypatch, _response({"answer": ANSWER, "sources": [],
                                             "latency_seconds": 3.2, "status": "ok"}))

    _reply()

    assert calls[0]["timeout"] == settings.API_TIMEOUT_SECONDS
    assert calls[0]["timeout"] > 5


# =====================================================
# THE BACKEND URL IS CONFIGURATION, NOT CODE
# =====================================================

def test_changing_the_configured_url_changes_where_the_question_goes(monkeypatch):
    """Acceptance test: a new backend URL needs no code change."""

    monkeypatch.setattr(settings, "API_BASE_URL", "http://elsewhere:9000")

    calls = _capture(monkeypatch, _response({"answer": ANSWER, "sources": [],
                                             "latency_seconds": 3.2, "status": "ok"}))

    _reply()

    assert calls[0]["url"] == "http://elsewhere:9000/chat"


# =====================================================
# EVERY 200 IS AN ANSWER
# =====================================================

@pytest.mark.parametrize("status", ["ok", "no_results", "guardrail"])
def test_every_successful_status_renders_its_answer(monkeypatch, status):
    """no_results and guardrail carry a real message; empty sources is not a failure."""

    text = "I can only assist with New Zealand workplace health and safety questions."

    _capture(monkeypatch, _response({"answer": text, "sources": [],
                                     "latency_seconds": 0.1, "status": status}))

    assert _reply("What is the capital of France?") == text


# =====================================================
# FAILURES DO NOT REACH THE USER RAW
# =====================================================

def test_an_unreachable_backend_falls_back_instead_of_raising(monkeypatch):
    def refuse(url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(responder.httpx, "post", refuse)

    assert _reply() == responder.FALLBACK_REPLY.strip()


def test_a_timeout_falls_back_instead_of_raising(monkeypatch):
    def time_out(url, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(responder.httpx, "post", time_out)

    assert _reply() == responder.FALLBACK_REPLY.strip()


def test_a_server_error_does_not_show_the_user_the_server_message(monkeypatch):
    _capture(monkeypatch, _response(
        {"status": "error",
         "message": "Something went wrong while answering that question."},
        status_code=500,
    ))

    reply = _reply()

    assert reply == responder.FALLBACK_REPLY.strip()
    assert "Something went wrong" not in reply


def test_a_validation_error_falls_back(monkeypatch):
    _capture(monkeypatch, _response(
        {"status": "error", "message": "A question is required."},
        status_code=422,
    ))

    assert _reply("") == responder.FALLBACK_REPLY.strip()
