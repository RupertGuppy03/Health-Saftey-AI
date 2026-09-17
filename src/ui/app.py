"""The Health & Safety AI chat interface.

The only module that draws the page. It renders the conversation, takes the next
question and streams the reply back while displaying the source metadata
returned with it. Everything to do with answering lives behind the responder,
so the pipeline can be connected without touching the layout.

Run it from the repo root with:  streamlit run streamlit_app.py
"""

from itertools import groupby
from operator import itemgetter
from pathlib import Path

import streamlit as st

from src.ui import browser_store, corpus, state, voice
from src.ui.responder import fetch_reply, stream_answer

PAGE_TITLE = "Health & Safety AI"
PAGE_ICON = "🦺"
ASSISTANT_AVATAR = "🦺"

GREETING = "What would you like to know?"
INPUT_PLACEHOLDER = "Want to ask about NZ health and safety?"
QUESTION_KEY = "hs_question"

SIDEBAR_BLURB = "Guidance from First Step Solutions"
DOCUMENTS_LABEL = "Documents"
DOCUMENTS_BLURB = "The guidance answers are drawn from. Download one to read it yourself and see where the sources are drawn from."
NO_DOCUMENTS = "No documents found under data/raw/."
NO_SUPPORTING_GUIDANCE = "No supporting guidance was found in the retrieved documents."

# What the user is told after recording a question by voice (story 13).
VOICE_NOTICES = {
    voice.HEARD: "Check the transcript, then press Enter to send.",
    voice.NOTHING_HEARD: "I didn't catch anything. Try recording again, or type your question.",
    voice.FAILED: "Voice input isn't available right now. Please type your question.",
}

STYLES = Path(__file__).with_name("styles.css")

# The surface behind a user bubble and the chat bar, per theme. These mirror
# secondaryBackgroundColor in .streamlit/config.toml, which Streamlit applies to
# its own widgets but does not publish to CSS for us to reuse.
SURFACE = {"light": "#F4F4F4", "dark": "#303030"}


def _active_theme():
    """ "light" or "dark", or None if Streamlit cannot say (e.g. under AppTest)."""

    try:
        return st.context.theme.type
    except Exception:
        return None


def _apply_styles():
    """Load the stylesheet that gives Streamlit its ChatGPT-like shape.

    The stylesheet falls back to the browser's colour-scheme preference, so the
    override is only needed when the viewer has picked a theme explicitly in
    Streamlit's settings.
    """

    css = STYLES.read_text(encoding="utf-8")
    surface = SURFACE.get(_active_theme())  # type: ignore

    if surface:
        css += f"\n:root {{ --hs-surface: {surface}; }}\n"

    st.html(f"<style>{css}</style>")


# =====================================================
# SIDEBAR
# =====================================================


def _open_pdf(path):
    """A no-argument reader for st.download_button.

    Passing the callable rather than the bytes means a PDF is only read when
    someone actually clicks it, so listing 25 large files costs nothing.
    """

    return lambda: path.read_bytes()


def _render_clear_control():
    if st.sidebar.button("Clear conversation", type="secondary"):
        state.clear_messages()
        st.rerun()


def _render_sidebar():
    """Branding, and the source documents the answers are drawn from.

    The document list is folded away behind a dropdown: there are 25 of them,
    which is more than the sidebar can show at once without becoming the page.
    """

    with st.sidebar:
        st.markdown(f"### {PAGE_TITLE}")
        st.caption(SIDEBAR_BLURB)

        _render_clear_control()

        documents = corpus.list_documents()

        # No custom icon: Streamlit puts one where the chevron goes, which
        # leaves a closed dropdown looking like it does not open.
        with st.expander(f"{DOCUMENTS_LABEL} ({len(documents)})"):
            if not documents:
                st.caption(NO_DOCUMENTS)
                return

            st.caption(DOCUMENTS_BLURB)

            # The list gets its own container so the stylesheet can tighten the
            # spacing between entries without touching the rest of the sidebar.
            with st.container(key="hs_documents"):
                for label, group in groupby(
                    documents, key=itemgetter("industry_label")
                ):
                    st.caption(label)

                    for document in group:
                        path = document["path"]

                        st.download_button(
                            document["title"],
                            data=_open_pdf(path),
                            file_name=path.name,
                            mime="application/pdf",
                            key=f"doc_{document['industry']}_{path.stem}",
                            help=f"Open {path.name}",
                            icon=":material/description:",
                            type="tertiary",
                            width="stretch",
                        )


# =====================================================
# CONVERSATION
# =====================================================


def _render_message(message):
    """Draw one stored message in its own bubble."""

    avatar = ASSISTANT_AVATAR if message["role"] == state.ASSISTANT else None

    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

        if message["role"] != state.ASSISTANT:
            return

        _render_sources(message.get("sources", []))


def _citation_entries(sources):
    """Collapse chunks by document and section into readable citation lines."""

    grouped = {}

    for source in sources:
        source_file = source.get("source_file") or "Unknown document"
        section = source.get("section_heading") or "Section heading unavailable"
        key = (source_file, section)
        pages = grouped.setdefault(key, set())

        if source.get("page_number") is not None:
            pages.add(source["page_number"])

    entries = []

    for (source_file, section), pages in grouped.items():
        title = corpus.document_title(source_file)
        if pages:
            page_values = ", ".join(str(page) for page in sorted(pages))
            page_reference = (
                f"page {page_values}" if len(pages) == 1 else f"pages {page_values}"
            )
        else:
            page_reference = "page reference unavailable"

        entries.append(f"- **{title}** — {page_reference}; section: {section}")

    return entries


def _render_sources(sources):
    """Render the source block separately from the answer text."""

    with st.container(border=True):
        st.caption("Sources")
        entries = _citation_entries(sources)

        if not entries:
            st.caption(NO_SUPPORTING_GUIDANCE)
            return

        for entry in entries:
            st.markdown(entry)


def _render_conversation(messages):
    """The whole history, oldest first, plus a reply if the last turn needs one.

    A trailing user message is one that has just been asked and not yet
    answered, so its reply is streamed in here rather than stored ahead of
    time. That way the user watches it arrive.
    """

    with st.container(key="hs_messages"):
        for message in messages:
            _render_message(message)

        if messages[-1]["role"] != state.USER:
            return

        # The reply's bubble is opened before the backend is called, not after. On
        # the first question the page swaps the greeting for the conversation, and
        # Streamlit leaves whatever has not been redrawn yet on screen, faded. The
        # bubble takes the old chat bar's place, so without this the bar and its
        # transcript linger for the whole ~30s wait.
        with st.chat_message(state.ASSISTANT, avatar=ASSISTANT_AVATAR):
            response = fetch_reply(messages[-1]["content"], messages[:-1])
            reply = st.write_stream(stream_answer(response["answer"]))
            _render_sources(response.get("sources", []))

        state.add_message(
            state.ASSISTANT,
            reply,
            sources=response.get("sources", []),
            status=response.get("status"),
        )


# =====================================================
# INPUT
# =====================================================


def _submit_question():
    question = st.session_state.get(QUESTION_KEY, "").strip()

    if not question:
        return

    messages = state.get_messages()

    if messages and messages[-1]["role"] == state.USER:
        if messages[-1]["content"] == question:
            return

    state.add_message(state.USER, question)


def _render_chat_input():
    """The question box, with its mic button and what came of the last recording.

    The recording is handled before the input is drawn, because a transcript can
    only be written into the input before the widget exists in this run.
    """

    with st.container(key="hs_chat_bar"):
        voice.take_recording(st.container(key="hs_voice"), QUESTION_KEY)

        notice = voice.pop_notice()

        if notice:
            st.caption(VOICE_NOTICES[notice])

        st.chat_input(INPUT_PLACEHOLDER, key=QUESTION_KEY, on_submit=_submit_question)


def _render_empty_state():
    """The first thing a user sees: a greeting with the input under it."""

    with st.container(key="hs_hero"):
        st.title(GREETING, anchor=False)

        _render_chat_input()


# =====================================================
# PAGE
# =====================================================


def main():
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="centered",
        initial_sidebar_state="expanded",
    )

    _apply_styles()
    _render_sidebar()
    state.init_state()

    # One fixed, hidden slot for the browser copy, so loading and saving mount
    # the same element. Until the tab's copy arrives after a reload, draw nothing:
    # a greeting would flash, and saving an empty history would overwrite it.
    store_slot = st.container(key="hs_store")

    if not browser_store.restore(store_slot):
        return

    try:
        messages = state.get_messages()

        if not messages:
            _render_empty_state()
            return

        # Once the conversation has started the input drops to the foot of the page.
        # It is drawn before the messages so that it stays on screen while a reply
        # streams in; st.bottom pins it there whatever the script order.
        with st.bottom:
            _render_chat_input()

        _render_conversation(messages)

    finally:
        # Saved after rendering so a reply stored during this run is included.
        browser_store.save(store_slot, state.get_messages())


if __name__ == "__main__":
    main()
