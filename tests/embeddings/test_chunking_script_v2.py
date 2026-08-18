"""Tests for chunking, OpenAI embedding and ChromaDB ingestion.

No test here touches the real OpenAI API. Embedding calls go through a stub
client injected via the `client=` parameter, and ingestion uses an in-memory
Chroma collection, so the suite is free to run and never writes to
`vectorstore/`.
"""

import json
from types import SimpleNamespace
from uuid import uuid4

import chromadb
import pytest

from src.embeddings import chunking_script_v2 as chunking


# =====================================================
# STUBS AND FIXTURES
# =====================================================

class StubEmbeddingsAPI:
    """Stands in for client.embeddings, recording what it was asked to embed."""

    def __init__(self, dimensions=chunking.EMBEDDING_DIMENSIONS):
        self.dimensions = dimensions
        self.calls = []

    def create(self, model, input):
        self.calls.append(list(input))

        data = [
            SimpleNamespace(
                index=position,
                # Encode the position in the vector so tests can prove ordering.
                embedding=[float(position + 1)] * self.dimensions,
            )
            for position in range(len(input))
        ]

        # Deliberately hand the items back out of order. The API does not
        # promise response order, and embed_texts must sort by .index.
        return SimpleNamespace(data=list(reversed(data)))


class StubOpenAIClient:
    def __init__(self, dimensions=chunking.EMBEDDING_DIMENSIONS):
        self.embeddings = StubEmbeddingsAPI(dimensions)

    @property
    def calls(self):
        return self.embeddings.calls


# Mirrors the shape of data/processed/*-CLEANED.json: a flat list of elements.
# Record 0 has no section_heading, like the front matter in five real documents.
CLEANED_ELEMENTS = [
    {
        "text": "This guideline provides practical guidance.",
        "source_file": "doc-a.pdf",
        "page_number": 1,
        "element_type": "NarrativeText",
        "section_heading": "",
        "chunk_type": "prose",
    },
    {
        "text": "Working at height",
        "source_file": "doc-a.pdf",
        "page_number": 2,
        "element_type": "Title",
        "section_heading": "Working at height",
        "chunk_type": "prose",
    },
    {
        "text": "Use edge protection wherever it is reasonably practicable.",
        "source_file": "doc-a.pdf",
        "page_number": 2,
        "element_type": "NarrativeText",
        "section_heading": "Working at height",
        "chunk_type": "prose",
    },
    {
        "text": "| Hazard | Control |\n| Fall | Guardrail |",
        "source_file": "doc-a.pdf",
        "page_number": 3,
        "element_type": "Table",
        "section_heading": "Hazard summary",
        "chunk_type": "table",
    },
]


@pytest.fixture
def cleaned_file(tmp_path):
    path = tmp_path / "doc-a-CLEANED.json"
    path.write_text(json.dumps(CLEANED_ELEMENTS), encoding="utf-8")
    return path


@pytest.fixture
def chunks(tmp_path, cleaned_file):
    # Small thresholds so this handful of short fixture elements still
    # produces multiple distinct chunks, the way a real multi-thousand
    # character document would under the real defaults.
    return chunking.chunk_document(
        cleaned_file,
        tmp_path / "doc-a-CHUNKS.json",
        target_chars=40,
        max_chars=200,
        min_chars=10,
        overlap_chars=0,
    )


@pytest.fixture
def memory_collection(monkeypatch):
    """An in-memory Chroma collection standing in for the persisted one.

    chromadb.EphemeralClient() returns a system shared across the process, so a
    fixed collection name would leak records between tests and make them
    order-dependent. Give each test its own collection instead.
    """

    client = chromadb.EphemeralClient()
    name = f"test_ingest_{uuid4().hex}"
    collection = client.get_or_create_collection(name)
    monkeypatch.setattr(chunking, "get_collection", lambda _name=None: collection)

    yield collection

    client.delete_collection(name)


# =====================================================
# CHUNKING
# =====================================================

def test_every_chunk_has_the_required_metadata(chunks):
    for chunk in chunks:
        for field in ("chunk_id", "text", "source_file", "page_number", "section_heading"):
            assert field in chunk, f"{field} missing from {chunk}"
            assert str(chunk[field]).strip(), f"{field} empty on {chunk['chunk_id']}"


def test_metadata_field_names_match_the_sprint_1_contract(chunks):
    # Story 2 DoD: the locked field names must still be exactly as Sprint 1
    # defined them. page_start/page_end are additive.
    assert set(chunks[0]) <= {
        "chunk_id",
        "text",
        "source_file",
        "page_number",
        "page_start",
        "page_end",
        "section_heading",
        "chunk_type",
    }


def test_table_elements_are_always_typed_table(chunks):
    # chunk_document derives section_heading from Title elements it walks, not
    # from the input record's own section_heading field, so a table's chunk
    # inherits whatever heading is in force rather than the fixture's label.
    table_chunks = [c for c in chunks if "| Hazard |" in c["text"]]

    assert table_chunks
    assert all(c["chunk_type"] == "table" for c in table_chunks)


def test_empty_section_heading_is_backfilled(chunks):
    assert all(c["section_heading"].strip() for c in chunks)
    assert any(
        c["section_heading"] == chunking.FALLBACK_SECTION_HEADING for c in chunks
    )


def test_front_matter_is_not_merged_into_the_next_heading(chunks):
    """Regression test.

    Several real documents open with untitled front matter followed by an
    acknowledgements list, so taking "the next heading" would file the front
    matter under something like '> Beca Ltd' — a false citation.
    """

    front_matter = [c for c in chunks if "practical guidance" in c["text"]]

    assert len(front_matter) == 1
    assert front_matter[0]["section_heading"] == chunking.FALLBACK_SECTION_HEADING


def test_chunk_ids_are_unique_within_a_document(chunks):
    ids = [c["chunk_id"] for c in chunks]

    assert len(ids) == len(set(ids))


def test_output_file_matches_the_returned_chunks(tmp_path, cleaned_file):
    output = tmp_path / "out.json"
    returned = chunking.chunk_document(cleaned_file, output)

    assert json.loads(output.read_text(encoding="utf-8")) == returned


def _element(text, page_number, element_type="NarrativeText", source_file="long.pdf"):
    return {
        "text": text,
        "source_file": source_file,
        "page_number": page_number,
        "element_type": element_type,
        "section_heading": "",
        "chunk_type": "prose",
    }


def test_many_small_elements_are_packed_up_to_the_target(tmp_path):
    # 40 elements of ~25 chars each, well past target_chars=200 in aggregate,
    # each far too small to be its own chunk under the real 300-char minimum.
    records = [_element(f"Sentence number {i} here.", 1) for i in range(40)]
    source = tmp_path / "long-CLEANED.json"
    source.write_text(json.dumps(records), encoding="utf-8")

    produced = chunking.chunk_document(
        source,
        tmp_path / "long-CHUNKS.json",
        target_chars=200,
        max_chars=300,
        min_chars=50,
        overlap_chars=0,
    )

    assert len(produced) > 1
    assert all(len(c["text"]) <= 300 for c in produced)
    assert all(len(c["text"]) >= 50 for c in produced[:-1])  # last may be a short remainder


def test_consecutive_chunks_share_overlap_text(tmp_path):
    records = [_element(f"Sentence number {i} about site safety here today.", 1) for i in range(30)]
    source = tmp_path / "overlap-CLEANED.json"
    source.write_text(json.dumps(records), encoding="utf-8")

    produced = chunking.chunk_document(
        source,
        tmp_path / "overlap-CHUNKS.json",
        target_chars=200,
        max_chars=400,
        min_chars=50,
        overlap_chars=100,
    )

    assert len(produced) > 1
    # The tail of one chunk should reappear at the head of the next.
    first_tail_words = produced[0]["text"].split()[-5:]
    assert " ".join(first_tail_words) in produced[1]["text"]


def test_page_start_and_end_span_a_multi_page_chunk(tmp_path):
    records = [
        _element("Row one of the section.", 5),
        _element("Row two, still the same section.", 5),
        _element("Row three, now on the next page.", 6),
    ]
    source = tmp_path / "pages-CLEANED.json"
    source.write_text(json.dumps(records), encoding="utf-8")

    # Thresholds high enough that all three elements land in one chunk.
    produced = chunking.chunk_document(
        source, tmp_path / "pages-CHUNKS.json", target_chars=1000, min_chars=1000
    )

    assert len(produced) == 1
    chunk = produced[0]
    assert chunk["page_start"] == 5
    assert chunk["page_end"] == 6
    assert chunk["page_number"] == chunk["page_start"]


# =====================================================
# VALIDATION
# =====================================================

def test_validate_chunks_accepts_good_chunks(chunks):
    chunking.validate_chunks(chunks)


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(lambda c: c.pop("section_heading"), id="missing_field"),
        pytest.param(lambda c: c.update(section_heading=None), id="null_value"),
        pytest.param(lambda c: c.update(section_heading="   "), id="blank_value"),
        pytest.param(lambda c: c.pop("chunk_id"), id="missing_chunk_id"),
    ],
)
def test_validate_chunks_rejects_bad_metadata(chunks, mutation):
    mutation(chunks[0])

    with pytest.raises(ValueError):
        chunking.validate_chunks(chunks)


# =====================================================
# EMBEDDING
# =====================================================

def test_embed_texts_batches_instead_of_one_call_per_chunk():
    client = StubOpenAIClient()
    texts = [f"chunk {i}" for i in range(300)]

    chunking.embed_texts(texts, batch_size=128, client=client)

    assert len(client.calls) == 3, "expected 3 batched calls, not one per text"
    assert [len(c) for c in client.calls] == [128, 128, 44]


def test_embed_texts_returns_one_vector_per_text_at_full_width():
    client = StubOpenAIClient()
    texts = [f"chunk {i}" for i in range(10)]

    vectors = chunking.embed_texts(texts, client=client)

    assert len(vectors) == len(texts)
    assert all(len(v) == chunking.EMBEDDING_DIMENSIONS for v in vectors)


def test_embed_texts_preserves_input_order():
    # The stub returns each batch reversed, so this fails if embed_texts
    # trusts the response order instead of sorting by .index.
    client = StubOpenAIClient()

    vectors = chunking.embed_texts([f"chunk {i}" for i in range(300)], batch_size=128,
                                   client=client)

    assert vectors[0][0] == 1.0
    assert vectors[1][0] == 2.0
    assert vectors[128][0] == 1.0, "second batch should restart at position 1"


def test_embed_texts_makes_no_call_for_empty_input():
    client = StubOpenAIClient()

    assert chunking.embed_texts([], client=client) == []
    assert client.calls == []


def test_embed_texts_rejects_unexpected_dimensions():
    client = StubOpenAIClient(dimensions=384)

    with pytest.raises(ValueError, match="dimension"):
        chunking.embed_texts(["anything"], client=client)


def test_batches_are_split_again_when_they_exceed_the_token_cap():
    oversized = ["word " * 30_000] * 4

    batches = chunking._split_into_batches(oversized, batch_size=128)

    assert len(batches) > 1, "token cap should override the count-based batch size"


def test_batches_respect_the_count_limit():
    batches = chunking._split_into_batches([f"t{i}" for i in range(300)], batch_size=50)

    assert all(len(b) <= 50 for b in batches)
    assert sum(len(b) for b in batches) == 300


# =====================================================
# API KEY RESOLUTION
# =====================================================

@pytest.fixture
def no_dotenv(monkeypatch):
    """Stop load_dotenv repopulating the environment from the real .env."""

    monkeypatch.setattr(chunking, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("OPEN_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_project_key_name_is_accepted(no_dotenv, monkeypatch):
    monkeypatch.setenv("OPEN_AI_API_KEY", "sk-project-name")

    assert chunking._get_openai_client().api_key == "sk-project-name"


def test_sdk_key_name_is_accepted_as_a_fallback(no_dotenv, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-sdk-name")

    assert chunking._get_openai_client().api_key == "sk-sdk-name"


def test_project_key_name_wins_when_both_are_set(no_dotenv, monkeypatch):
    monkeypatch.setenv("OPEN_AI_API_KEY", "sk-project-name")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-sdk-name")

    assert chunking._get_openai_client().api_key == "sk-project-name"


def test_missing_key_raises_an_actionable_error(no_dotenv):
    with pytest.raises(RuntimeError, match="OPEN_AI_API_KEY"):
        chunking._get_openai_client()


# =====================================================
# CHROMADB INGESTION
# =====================================================

@pytest.fixture
def chunk_file(tmp_path, chunks):
    path = tmp_path / "ingest-CHUNKS.json"
    path.write_text(json.dumps(chunks), encoding="utf-8")
    return path


def test_ingest_stores_every_chunk(chunk_file, memory_collection, chunks):
    summary = chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    assert memory_collection.count() == len(chunks)
    assert summary["chunks_embedded"] == len(chunks)
    assert summary["count_before"] == 0
    assert summary["count_after"] == len(chunks)
    assert summary["embedding_model"] == chunking.EMBEDDING_MODEL


def test_ingest_uses_deterministic_ids(chunk_file, memory_collection, chunks):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    assert sorted(memory_collection.get()["ids"]) == sorted(chunking.build_chunk_ids(chunks))


def test_ids_are_stable_across_builds(chunks):
    assert chunking.build_chunk_ids(chunks) == chunking.build_chunk_ids(chunks)


def test_id_format_is_stem_page_index():
    record_id = chunking._chunk_record_id("PCBUs-Working-Together-GPG-7fcb7c71.pdf", 9, 42)

    assert record_id == "PCBUs-Working-Together-GPG-7fcb7c71:p0009:0042"


def test_ids_do_not_collide_between_documents():
    # chunk_id restarts at CHUNK_00001 in every file, so the ID must be built
    # from the document itself rather than from that counter.
    assert chunking._chunk_record_id("doc-a.pdf", 1, 0) != chunking._chunk_record_id("doc-b.pdf", 1, 0)


def test_ids_do_not_collide_within_a_page(chunks):
    ids = chunking.build_chunk_ids(chunks)

    assert len(ids) == len(set(ids))


def test_ids_ignore_the_chunk_id_counter(chunks):
    renumbered = [dict(c, chunk_id="CHUNK_99999") for c in chunks]

    assert chunking.build_chunk_ids(renumbered) == chunking.build_chunk_ids(chunks)


def test_ingest_stores_the_expected_metadata(chunk_file, memory_collection, chunks):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    stored = memory_collection.get(include=["metadatas", "documents"])
    by_id = dict(zip(stored["ids"], stored["metadatas"]))

    for chunk, record_id in zip(chunks, chunking.build_chunk_ids(chunks)):
        metadata = by_id[record_id]

        assert metadata["source_file"] == chunk["source_file"]
        assert metadata["page_number"] == chunk["page_number"]
        assert metadata["section_heading"] == chunk["section_heading"]


def test_no_stored_record_has_an_empty_metadata_field(chunk_file, memory_collection):
    # Story 2 DoD: no chunk is stored with a missing or empty metadata field.
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    for metadata in memory_collection.get(include=["metadatas"])["metadatas"]:
        for field in ("source_file", "page_number", "section_heading"):
            assert field in metadata
            assert str(metadata[field]).strip()


def test_ingesting_twice_does_not_duplicate_records(chunk_file, memory_collection, chunks):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())
    first = memory_collection.count()

    second_summary = chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    assert memory_collection.count() == first == len(chunks)
    assert second_summary["count_before"] == second_summary["count_after"]


def test_a_chunk_id_returns_exactly_one_record(chunk_file, memory_collection, chunks):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    target = chunking.build_chunk_ids(chunks)[0]

    assert len(memory_collection.get(ids=[target])["ids"]) == 1


def test_invalid_chunks_fail_before_any_embedding_is_paid_for(tmp_path, memory_collection):
    bad = [{"chunk_id": "CHUNK_00001", "text": "x", "source_file": "d.pdf",
            "page_number": 1, "section_heading": ""}]
    path = tmp_path / "bad-CHUNKS.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    client = StubOpenAIClient()

    with pytest.raises(ValueError):
        chunking.ingest_to_chromadb(path, client=client)

    assert client.calls == [], "validation must run before the API is called"


# =====================================================
# STALE PRUNING AND PROVENANCE (STORY 3)
# =====================================================

def _write_chunks(path, count, source_file="doc-a.pdf"):
    """A chunk file with `count` chunks, as chunk_document would emit."""

    records = [
        {
            "chunk_id": f"CHUNK_{i + 1:05}",
            "text": f"chunk text {i}",
            "source_file": source_file,
            "page_number": (i % 3) + 1,
            "section_heading": f"Section {i}",
            "chunk_type": "prose",
        }
        for i in range(count)
    ]
    path.write_text(json.dumps(records), encoding="utf-8")
    return records


def test_shrinking_a_document_removes_the_orphans(tmp_path, memory_collection):
    """Acceptance test 3: changed config re-embeds rather than leaving stale records.

    upsert only overwrites IDs that still exist, so without pruning the two
    dropped chunks would stay in the collection and keep being retrieved.
    """

    big = tmp_path / "big-CHUNKS.json"
    _write_chunks(big, 5)
    chunking.ingest_to_chromadb(big, client=StubOpenAIClient())
    before = set(memory_collection.get()["ids"])

    small = tmp_path / "small-CHUNKS.json"
    smaller_chunks = _write_chunks(small, 3)
    summary = chunking.ingest_to_chromadb(small, client=StubOpenAIClient())

    after = set(memory_collection.get()["ids"])

    assert memory_collection.count() == 3
    assert summary["stale_removed"] == 2
    assert after == set(chunking.build_chunk_ids(smaller_chunks))
    assert not (after - before), "no unexpected ids introduced"


def test_pruning_leaves_other_documents_alone(tmp_path, memory_collection):
    other = tmp_path / "other-CHUNKS.json"
    _write_chunks(other, 4, source_file="doc-b.pdf")
    chunking.ingest_to_chromadb(other, client=StubOpenAIClient())

    mine = tmp_path / "mine-CHUNKS.json"
    _write_chunks(mine, 2, source_file="doc-a.pdf")
    chunking.ingest_to_chromadb(mine, client=StubOpenAIClient())

    doc_b = memory_collection.get(where={"source_file": "doc-b.pdf"})["ids"]

    assert len(doc_b) == 4


def test_nothing_is_pruned_on_an_unchanged_rerun(tmp_path, memory_collection):
    path = tmp_path / "same-CHUNKS.json"
    _write_chunks(path, 4)
    chunking.ingest_to_chromadb(path, client=StubOpenAIClient())

    summary = chunking.ingest_to_chromadb(path, client=StubOpenAIClient())

    assert summary["stale_removed"] == 0
    assert summary["count_before"] == summary["count_after"] == 4


def test_records_carry_the_pipeline_provenance(chunk_file, memory_collection):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    metadata = memory_collection.get(include=["metadatas"])["metadatas"][0]

    assert metadata["pipeline_version"] == chunking.PIPELINE_VERSION
    assert metadata["embedding_model"] == chunking.EMBEDDING_MODEL
    assert metadata["chunk_target_chars"] == chunking.CHUNK_TARGET_CHARS
    assert metadata["chunk_overlap_chars"] == chunking.CHUNK_OVERLAP_CHARS


def test_provenance_reflects_the_config_actually_used(chunk_file, memory_collection):
    chunking.ingest_to_chromadb(
        chunk_file, target_chars=1000, overlap_chars=200, client=StubOpenAIClient()
    )

    metadata = memory_collection.get(include=["metadatas"])["metadatas"][0]

    assert metadata["chunk_target_chars"] == 1000
    assert metadata["chunk_overlap_chars"] == 200


def test_provenance_does_not_displace_the_locked_schema(chunk_file, memory_collection):
    chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    for metadata in memory_collection.get(include=["metadatas"])["metadatas"]:
        for field in ("source_file", "page_number", "section_heading"):
            assert str(metadata[field]).strip()


def test_summary_reports_what_happened(chunk_file, memory_collection, chunks):
    summary = chunking.ingest_to_chromadb(chunk_file, client=StubOpenAIClient())

    assert summary["chunks_embedded"] == len(chunks)
    assert summary["stale_removed"] == 0
    assert summary["pipeline_version"] == chunking.PIPELINE_VERSION


# =====================================================
# ADAPTIVE HEADING DETECTION (CHUNKING QUALITY FIX)
# =====================================================

def test_numbered_headings_are_always_structural():
    assert chunking._is_structural_heading("1.3 Contracting duties")
    assert chunking._is_structural_heading("2. Scope")


def test_short_all_caps_lines_are_structural():
    assert chunking._is_structural_heading("KEY POINTS")


def test_a_long_all_caps_line_is_not_structural():
    shouting = "THIS LINE IS DELIBERATELY WRITTEN TO BE MUCH TOO LONG TO EVER COUNT AS A REAL SECTION HEADING LABEL"
    assert len(shouting) > 80  # guards the test itself against silently shrinking below the cap
    assert not chunking._is_structural_heading(shouting)


def test_mid_sentence_fragments_do_not_look_like_structural_headings():
    # The exact class of fragment that caused the original bug: a PDF line
    # wrap tagged Title by the extractor, capitalised only by coincidence.
    assert not chunking._is_structural_heading("Work Act 2015 (HSWA), illustrate different")


@pytest.mark.parametrize(
    "text",
    [
        "your duties under the Health and Safety at",  # starts lowercase: a continuation
        "Use of the guide, illustrate different points.",  # ends in a full stop: a real sentence
    ],
)
def test_looks_like_heading_shape_rejects_fragment_shapes(text):
    assert not chunking._looks_like_heading_shape(text)


def test_looks_like_heading_shape_accepts_a_short_title_case_label():
    assert chunking._looks_like_heading_shape("Key terms")
    assert chunking._looks_like_heading_shape("Emergency procedures")


def test_is_section_heading_requires_a_finished_previous_sentence_for_shape_matches():
    # "Work Act 2015 (HSWA), illustrate different" only looks heading-shaped
    # because "Work" happens to be capitalised — it is really a continuation
    # of the unfinished previous line, so it must be rejected...
    assert not chunking.is_section_heading(
        "Work Act 2015 (HSWA), illustrate different",
        allow_shape=True,
        previous_text="your duties under the Health and Safety at",
    )
    # ...but the same text is accepted when the true previous sentence ends
    # properly, since then it really could be a new short heading.
    assert chunking.is_section_heading(
        "Emergency procedures", allow_shape=True, previous_text="All work must stop."
    )


def test_is_section_heading_ignores_the_continuation_gate_for_structural_headings():
    # A numbered heading is unambiguous regardless of what came before it.
    assert chunking.is_section_heading(
        "1.3 Contracting duties", allow_shape=True, previous_text="mid-sentence fragment"
    )


def test_detect_allow_heading_shape_is_false_for_a_numbering_heavy_document():
    records = [
        {"element_type": "Title", "text": t}
        for t in ["1.1 Purpose", "1.2 Scope", "2.1 Duties", "SAFETY", "KEY POINTS"]
    ]
    assert chunking.detect_allow_heading_shape(records) is False


def test_detect_allow_heading_shape_is_true_for_a_title_case_document():
    records = [
        {"element_type": "Title", "text": t}
        for t in ["Key terms", "Emergency procedures", "Contact details", "Site rules"]
    ]
    assert chunking.detect_allow_heading_shape(records) is True


# =====================================================
# TABLES STAY ATOMIC (CHUNKING QUALITY FIX)
# =====================================================

TABLE_TEXT = "| A | B |\n| --- | --- |\n| 1 | 2 |"


def _table_element(text=TABLE_TEXT, page_number=1, source_file="doc.pdf"):
    return {
        "text": text,
        "source_file": source_file,
        "page_number": page_number,
        "element_type": "Table",
        "section_heading": "",
        "chunk_type": "table",
    }


def test_a_table_is_never_merged_with_surrounding_prose(tmp_path):
    records = [
        {"text": "A complete sentence about the site.", "source_file": "doc.pdf",
         "page_number": 1, "element_type": "NarrativeText", "section_heading": "", "chunk_type": "prose"},
        _table_element(),
        {"text": "Another complete sentence right after.", "source_file": "doc.pdf",
         "page_number": 1, "element_type": "NarrativeText", "section_heading": "", "chunk_type": "prose"},
    ]
    source = tmp_path / "table-CLEANED.json"
    source.write_text(json.dumps(records), encoding="utf-8")

    produced = chunking.chunk_document(source, tmp_path / "table-CHUNKS.json")

    table_chunks = [c for c in produced if c["chunk_type"] == "table"]
    assert len(table_chunks) == 1
    assert table_chunks[0]["text"] == TABLE_TEXT
    assert not any("sentence" in c["text"] for c in table_chunks)


def test_every_table_element_becomes_its_own_chunk(tmp_path):
    records = [_table_element(), _table_element(page_number=2), _table_element(page_number=3)]
    source = tmp_path / "tables-CLEANED.json"
    source.write_text(json.dumps(records), encoding="utf-8")

    produced = chunking.chunk_document(source, tmp_path / "tables-CHUNKS.json")

    assert len(produced) == 3
    assert all(c["chunk_type"] == "table" for c in produced)


def test_an_oversized_table_is_split_with_the_header_repeated(tmp_path):
    header = "| TERM | DEFINITION |\n| --- | --- |"
    rows = "\n".join(f"| word{i} | a fairly long definition line number {i} |" for i in range(80))
    big_table = f"{header}\n{rows}"

    records = [_table_element(text=big_table)]
    source = tmp_path / "bigtable-CLEANED.json"
    source.write_text(json.dumps(records), encoding="utf-8")

    produced = chunking.chunk_document(
        source, tmp_path / "bigtable-CHUNKS.json", max_chars=1000
    )

    assert len(produced) > 1
    assert all(c["chunk_type"] == "table" for c in produced)
    assert all(c["text"].startswith(header) for c in produced)
    assert all(len(c["text"]) <= 1000 + len(header) for c in produced)


def test_a_heading_only_lead_in_is_captioned_onto_its_table(tmp_path):
    records = [
        {"text": "Drawings", "source_file": "doc.pdf", "page_number": 1,
         "element_type": "Title", "section_heading": "", "chunk_type": "prose"},
        _table_element(),
    ]
    source = tmp_path / "caption-CLEANED.json"
    source.write_text(json.dumps(records), encoding="utf-8")

    produced = chunking.chunk_document(source, tmp_path / "caption-CHUNKS.json")

    assert len(produced) == 1
    assert produced[0]["chunk_type"] == "table"
    assert produced[0]["text"] == f"Drawings\n{TABLE_TEXT}"


def test_a_finished_sentence_is_not_treated_as_a_table_caption(tmp_path):
    # Regression test: the caption path must never absorb genuine prose just
    # because it happens to be short — only unfinished labels/fragments.
    records = [
        {"text": "This is a complete sentence.", "source_file": "doc.pdf", "page_number": 1,
         "element_type": "NarrativeText", "section_heading": "", "chunk_type": "prose"},
        _table_element(),
    ]
    source = tmp_path / "no-caption-CLEANED.json"
    source.write_text(json.dumps(records), encoding="utf-8")

    produced = chunking.chunk_document(source, tmp_path / "no-caption-CHUNKS.json")

    assert len(produced) == 2
    table_chunk = [c for c in produced if c["chunk_type"] == "table"][0]
    assert table_chunk["text"] == TABLE_TEXT
    prose_chunk = [c for c in produced if c["chunk_type"] != "table"][0]
    assert "complete sentence" in prose_chunk["text"]


# =====================================================
# ELEMENT ORDER AND NON-ADJACENT SECTIONS (CHUNKING QUALITY FIX)
# =====================================================

def test_non_adjacent_sections_sharing_a_heading_are_not_merged(tmp_path):
    # The old defaultdict-grouping chunker grouped by (source_file,
    # section_heading), so two non-adjacent sections with the same title text
    # would be silently combined even with unrelated content between them.
    records = [
        {"text": "1. Notes", "source_file": "doc.pdf", "page_number": 1,
         "element_type": "Title", "section_heading": "", "chunk_type": "prose"},
        {"text": "First occurrence content.", "source_file": "doc.pdf", "page_number": 1,
         "element_type": "NarrativeText", "section_heading": "", "chunk_type": "prose"},
        {"text": "2. Other section", "source_file": "doc.pdf", "page_number": 2,
         "element_type": "Title", "section_heading": "", "chunk_type": "prose"},
        {"text": "Unrelated content in between.", "source_file": "doc.pdf", "page_number": 2,
         "element_type": "NarrativeText", "section_heading": "", "chunk_type": "prose"},
        {"text": "1. Notes", "source_file": "doc.pdf", "page_number": 3,
         "element_type": "Title", "section_heading": "", "chunk_type": "prose"},
        {"text": "Second, unrelated occurrence content.", "source_file": "doc.pdf", "page_number": 3,
         "element_type": "NarrativeText", "section_heading": "", "chunk_type": "prose"},
    ]
    source = tmp_path / "repeat-CLEANED.json"
    source.write_text(json.dumps(records), encoding="utf-8")

    produced = chunking.chunk_document(
        source, tmp_path / "repeat-CHUNKS.json",
        target_chars=10, max_chars=10_000, min_chars=1, overlap_chars=0,
    )

    first = [c for c in produced if "First occurrence" in c["text"]]
    second = [c for c in produced if "Second, unrelated" in c["text"]]
    assert first and second
    assert first[0] is not second[0]
    assert "Unrelated content" not in first[0]["text"]
    assert "First occurrence" not in second[0]["text"]


def test_elements_are_read_in_document_order(tmp_path):
    records = [
        {"text": f"Element number {i}.", "source_file": "doc.pdf", "page_number": 1,
         "element_type": "NarrativeText", "section_heading": "", "chunk_type": "prose"}
        for i in range(5)
    ]
    source = tmp_path / "order-CLEANED.json"
    source.write_text(json.dumps(records), encoding="utf-8")

    produced = chunking.chunk_document(
        source, tmp_path / "order-CHUNKS.json", target_chars=10_000, min_chars=1
    )

    assert len(produced) == 1
    positions = [produced[0]["text"].index(f"Element number {i}.") for i in range(5)]
    assert positions == sorted(positions)
