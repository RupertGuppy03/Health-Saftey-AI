"""Behavioural tests for the chat page, driven by Streamlit's own AppTest.

The app is run in-process, with no browser and no server. Two things are
stubbed: the responder, so nothing tries to answer for real, and the corpus
listing, so the sidebar shows documents built under tmp_path rather than the
committed PDFs.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.ui import app as app_module
from src.ui import state

ENTRYPOINT = Path(__file__).resolve().parents[2] / "streamlit_app.py"

STUB_REPLY = "A stubbed answer."


# =====================================================
# FIXTURES
# =====================================================

def _stub_fetch(question, history=None):
    """Stands in for responder.fetch_reply: one answer with no sources."""

    return {"answer": STUB_REPLY, "sources": [], "status": "ok"}


@pytest.fixture
def documents(tmp_path):
    """Two source documents, shaped like corpus.list_documents() output."""

    entries = []

    for industry, filename, title in [
        ("building_and_construction", "excavation-safety-gpg.pdf", "Excavation Safety"),
        ("manufacturing", "safe-use-of-machinery-gpg.pdf", "Safe Use of Machinery"),
    ]:
        path = tmp_path / industry / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 not a real pdf")

        entries.append(
            {
                "industry": industry,
                "industry_label": industry.replace("_", " ").capitalize(),
                "title": title,
                "path": path,
            }
        )

    return entries


@pytest.fixture
def app(monkeypatch, documents):
    """The page, with the responder and the corpus listing stubbed out."""

    monkeypatch.setattr(app_module, "fetch_reply", _stub_fetch)
    monkeypatch.setattr(app_module.corpus, "list_documents", lambda *a, **k: documents)

    return AppTest.from_file(str(ENTRYPOINT), default_timeout=10)


def _ask(app, question):
    """Type a question into the chat box and submit it."""

    app.chat_input[0].set_value(question).run()

    return app


def _roles(app):
    return [message.name for message in app.chat_message]


def _texts(app):
    return [
        "".join(block.value for block in message.markdown) for message in app.chat_message
    ]


# =====================================================
# THE PAGE OPENS
# =====================================================

def test_the_page_runs_without_raising(app):
    app.run()

    assert not app.exception


def test_the_greeting_is_shown_before_anything_is_asked(app):
    app.run()

    assert app_module.GREETING in [title.value for title in app.title]


def test_there_are_no_messages_before_anything_is_asked(app):
    app.run()

    assert app.chat_message == []


# =====================================================
# ASKING A QUESTION
# =====================================================

def test_a_submitted_question_appears_as_a_user_message(app):
    app.run()
    _ask(app, "Do I need edge protection on a roof?")

    assert app.chat_message[0].name == state.USER
    assert "edge protection" in _texts(app)[0]


def test_the_reply_renders_as_an_assistant_message_below_the_question(app):
    app.run()
    _ask(app, "Do I need edge protection on a roof?")

    assert _roles(app) == [state.USER, state.ASSISTANT]
    assert STUB_REPLY in _texts(app)[1]


def test_an_answer_without_sources_explains_that_supporting_guidance_was_not_found(app):
    app.run()
    _ask(app, "Do I need edge protection on a roof?")

    captions = [caption.value for caption in app.chat_message[1].caption]

    assert app_module.NO_SUPPORTING_GUIDANCE in captions


def test_sources_show_document_page_and_section_and_collapse_duplicate_chunks(app, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "fetch_reply",
        lambda question, history=None: {
            "answer": STUB_REPLY,
            "status": "ok",
            "sources": [
                {
                    "source_file": "working-on-roofs.pdf",
                    "page_number": 4,
                    "section_heading": "Working at height",
                },
                {
                    "source_file": "working-on-roofs.pdf",
                    "page_number": 5,
                    "section_heading": "Working at height",
                },
            ],
        },
    )

    app.run()
    _ask(app, "Do I need edge protection on a roof?")

    markdown = _texts(app)[1]

    assert markdown.count("**Working on Roofs**") == 1
    assert "pages 4, 5" in markdown
    assert "section: Working at height" in markdown


def test_the_greeting_makes_way_for_the_conversation(app):
    app.run()
    _ask(app, "Do I need edge protection on a roof?")

    assert app_module.GREETING not in [title.value for title in app.title]


def test_several_exchanges_stay_in_the_order_they_were_sent(app):
    app.run()
    _ask(app, "First question")
    _ask(app, "Second question")
    _ask(app, "Third question")

    assert _roles(app) == [state.USER, state.ASSISTANT] * 3

    questions = [text for text in _texts(app) if "question" in text.lower()]
    assert questions == ["First question", "Second question", "Third question"]


def test_the_user_and_the_assistant_are_told_apart_by_role(app):
    # What the stylesheet keys off to give them different bubbles.
    app.run()
    _ask(app, "Do I need edge protection on a roof?")

    assert set(_roles(app)) == {state.USER, state.ASSISTANT}


def test_an_earlier_answer_is_not_regenerated_on_a_later_run(app):
    app.run()
    _ask(app, "First question")

    first_answer = _texts(app)[1]

    _ask(app, "Second question")

    assert _texts(app)[1] == first_answer


# =====================================================
# THE SIDEBAR
# =====================================================

def _documents_dropdown(app):
    """The collapsible the document list sits in."""

    return app.sidebar.expander[0]


def test_the_documents_are_folded_into_a_dropdown(app, documents):
    app.run()

    dropdown = _documents_dropdown(app)

    assert [button.label for button in dropdown.download_button] == [
        document["title"] for document in documents
    ]


def test_the_dropdown_says_how_many_documents_there_are(app, documents):
    app.run()

    assert _documents_dropdown(app).label == f"{app_module.DOCUMENTS_LABEL} ({len(documents)})"


def test_the_sidebar_lists_every_source_document(app, documents):
    app.run()

    labels = [button.label for button in app.sidebar.download_button]

    assert labels == [document["title"] for document in documents]


def test_each_document_downloads_under_its_own_filename(app, documents):
    app.run()

    # AppTest does not expose file_name, so check the keys, which are built
    # from the same industry and filename.
    keys = [button.key for button in app.sidebar.download_button]

    assert keys == [f"doc_{d['industry']}_{d['path'].stem}" for d in documents]


def test_the_sidebar_names_each_industry(app, documents):
    app.run()

    captions = [caption.value for caption in app.sidebar.caption]

    for document in documents:
        assert document["industry_label"] in captions


def test_the_page_still_opens_when_the_corpus_is_missing(monkeypatch):
    # A clean clone has no data/raw/, and the app must not fall over.
    monkeypatch.setattr(app_module, "fetch_reply", _stub_fetch)
    monkeypatch.setattr(app_module.corpus, "list_documents", lambda *a, **k: [])

    app = AppTest.from_file(str(ENTRYPOINT), default_timeout=10).run()

    assert not app.exception
    assert app_module.NO_DOCUMENTS in [caption.value for caption in app.sidebar.caption]


# =====================================================
# THE CONVERSATION IS THE SESSION'S OWN (story 10)
# =====================================================

def _recording_fetch(calls):
    """A responder stub that records the history it was handed."""

    def fetch(question, history=None):
        calls.append({"question": question, "history": [dict(turn) for turn in history or []]})
        return {"answer": STUB_REPLY, "sources": [], "status": "ok"}

    return fetch


@pytest.fixture
def two_sessions(monkeypatch, documents):
    """Two independent app instances, as two browsers on two machines would be."""

    monkeypatch.setattr(app_module.corpus, "list_documents", lambda *a, **k: documents)

    return (
        AppTest.from_file(str(ENTRYPOINT), default_timeout=10),
        AppTest.from_file(str(ENTRYPOINT), default_timeout=10),
    )


def test_the_earlier_conversation_is_sent_with_a_follow_up(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module, "fetch_reply", _recording_fetch(calls))

    app.run()
    _ask(app, "Do I need edge protection on a roof?")
    _ask(app, "What about on a smaller one?")

    assert calls[0]["history"] == []
    assert calls[1]["question"] == "What about on a smaller one?"
    # The reply is stored as it was streamed, so compare on the text not the spacing.
    assert [(turn["role"], turn["content"].strip()) for turn in calls[1]["history"]] == [
        (state.USER, "Do I need edge protection on a roof?"),
        (state.ASSISTANT, STUB_REPLY),
    ]


def test_one_session_never_sees_another_sessions_conversation(two_sessions, monkeypatch):
    """Acceptance: a conversation on one machine cannot affect one on another."""

    calls = []
    monkeypatch.setattr(app_module, "fetch_reply", _recording_fetch(calls))

    first, second = two_sessions

    first.run()
    _ask(first, "How do I remove asbestos safely?")

    second.run()
    _ask(second, "When must a scaffold be inspected?")

    _ask(first, "And what about the disposal?")

    # The second session asked its first question with nothing behind it, even
    # though the first session already had a conversation going.
    assert calls[1]["history"] == []

    # The first session's follow-up carries its own conversation and only its own.
    followed_up = " ".join(turn["content"] for turn in calls[2]["history"])
    assert "asbestos" in followed_up
    assert "scaffold" not in followed_up


def test_each_session_keeps_its_own_messages_on_screen(two_sessions, monkeypatch):
    monkeypatch.setattr(app_module, "fetch_reply", _stub_fetch)

    first, second = two_sessions

    first.run()
    _ask(first, "How do I remove asbestos safely?")

    second.run()
    _ask(second, "When must a scaffold be inspected?")

    assert "asbestos" in " ".join(_texts(first))
    assert "asbestos" not in " ".join(_texts(second))
    assert "scaffold" in " ".join(_texts(second))
    assert "scaffold" not in " ".join(_texts(first))


def test_the_history_is_not_cached_across_sessions():
    """A Streamlit cache is shared by every session, so messages must never be in one."""

    from src.ui import state

    source = Path(state.__file__).read_text(encoding="utf-8")

    assert "cache_data" not in source
    assert "cache_resource" not in source
