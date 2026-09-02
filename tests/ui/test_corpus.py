"""Tests for the source-document list behind the interface sidebar.

Nothing here reads a PDF or touches the real data/raw/. Documents are empty
files created under tmp_path, because the module only ever handles names and
paths. The filenames used are the real ones from the corpus, since their
inconsistent casing is exactly what the title rules have to cope with.
"""

import pytest

from src.ui import corpus


# =====================================================
# FIXTURES
# =====================================================

def _write_pdf(root, industry, slug, filename):
    """A document folder shaped like the real data/raw/<industry>/<slug>/."""

    folder = root / industry / slug
    folder.mkdir(parents=True, exist_ok=True)

    pdf = folder / filename
    pdf.write_bytes(b"%PDF-1.4 not a real pdf")

    return pdf


@pytest.fixture
def raw_dir(tmp_path):
    """Two industries, with one document filed under both."""

    root = tmp_path / "raw"

    _write_pdf(root, "building_and_construction", "excavation_safety",
               "excavation-safety-gpg.pdf")
    _write_pdf(root, "building_and_construction", "working_on_roofs",
               "working-on-roofs-GPG.pdf")
    _write_pdf(root, "building_and_construction", "exposure_monitoring",
               "exposure-monitoring-and-health-monitoring-gpg.pdf")
    _write_pdf(root, "manufacturing", "exposure_monitoring",
               "exposure-monitoring-and-health-monitoring-gpg.pdf")

    # A loose file at the industry level, as tidy-ups tend to leave behind.
    (root / "README.md").write_text("folder map", encoding="utf-8")

    return root


# =====================================================
# DOCUMENT TITLES
# =====================================================

@pytest.mark.parametrize(
    "filename, expected",
    [
        ("excavation-safety-gpg.pdf", "Excavation Safety"),
        ("working-on-roofs-GPG.pdf", "Working on Roofs"),
        ("Health-and-Safety-by-Design-GPG.pdf", "Health and Safety by Design"),
        ("scaffolding-in-New-Zealand-gpg.pdf", "Scaffolding in New Zealand"),
        ("managing-Work-Site-Traffic-GPG.pdf", "Managing Work Site Traffic"),
        ("working-with-or-near-asbestos-gpg.pdf", "Working with or near Asbestos"),
    ],
)
def test_real_filenames_become_readable_titles(filename, expected):
    assert corpus.document_title(filename) == expected


def test_the_shared_gpg_suffix_is_dropped():
    # Every file in the corpus ends in it, so it tells the reader nothing.
    assert "gpg" not in corpus.document_title("excavation-safety-gpg.pdf").lower()


def test_an_acronym_keeps_its_own_capitalisation():
    assert corpus.document_title("PCBUs-Working-Together-GPG.pdf") == "PCBUs Working Together"


def test_an_acronym_is_recovered_from_an_all_lowercase_filename():
    title = corpus.document_title("managing-asbestos-for-pcbus-gpg.pdf")

    assert title == "Managing Asbestos for PCBUs"


def test_a_small_word_is_capitalised_when_it_starts_the_title():
    assert corpus.document_title("in-the-workplace.pdf") == "In the Workplace"


# =====================================================
# INDUSTRY LABELS
# =====================================================

def test_an_industry_slug_becomes_a_heading():
    assert corpus.industry_label("building_and_construction") == "Building and Construction"


def test_a_single_word_industry_slug_is_capitalised():
    assert corpus.industry_label("manufacturing") == "Manufacturing"


# =====================================================
# LISTING
# =====================================================

def test_every_pdf_in_the_corpus_is_listed(raw_dir):
    assert len(corpus.list_documents(raw_dir)) == 4


def test_loose_files_outside_an_industry_folder_are_skipped(raw_dir):
    titles = [d["title"] for d in corpus.list_documents(raw_dir)]

    assert not any("README" in title for title in titles)


def test_each_entry_carries_its_industry_title_and_path(raw_dir):
    entry = corpus.list_documents(raw_dir)[0]

    for field in ("industry", "industry_label", "title", "path"):
        assert field in entry


def test_documents_are_sorted_by_industry_then_title(raw_dir):
    documents = corpus.list_documents(raw_dir)

    keys = [(d["industry"], d["title"]) for d in documents]

    assert keys == sorted(keys)


def test_a_document_filed_under_two_industries_appears_under_both(raw_dir):
    documents = corpus.list_documents(raw_dir)

    shared = [d for d in documents if d["title"].startswith("Exposure Monitoring")]

    assert {d["industry"] for d in shared} == {"building_and_construction", "manufacturing"}


def test_a_missing_corpus_folder_returns_nothing_rather_than_raising(tmp_path):
    # A clean clone has no data/raw/, and the app still has to open.
    assert corpus.list_documents(tmp_path / "not_here") == []


def test_an_empty_corpus_folder_returns_nothing(tmp_path):
    empty = tmp_path / "raw"
    empty.mkdir()

    assert corpus.list_documents(empty) == []


def test_the_path_points_at_a_file_that_exists(raw_dir):
    for document in corpus.list_documents(raw_dir):
        assert document["path"].is_file()
