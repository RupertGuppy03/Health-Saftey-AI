"""Offline checks for citations returned by the RAG pipeline."""

import sys
from types import ModuleType, SimpleNamespace

import pytest

from src.evaluation.citations import has_citation_source


def test_result_with_source_file_has_a_citation_source():
    assert has_citation_source(
        {"sources": [{"source_file": "working-on-roofs.pdf", "page_number": 4}]}
    )


def test_empty_sources_have_no_citation_source():
    assert not has_citation_source({"sources": []})


def test_missing_or_invalid_source_metadata_has_no_citation_source():
    assert not has_citation_source({})
    assert not has_citation_source({"sources": None})
    assert not has_citation_source(
        {
            "sources": [
                None,
                "not metadata",
                {"source_file": 42},
                {"source_file": ""},
                {"source_file": "  "},
                {"page_number": 4},
            ]
        }
    )


def test_dag_scorer_receives_answer_citations_and_retrieved_metadata(monkeypatch):
    from src.evaluation import citations

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured = {}

    class FakeNode:
        def __init__(self, **kwargs):
            captured["criteria"] = kwargs["criteria"]
            captured["verdicts"] = kwargs["children"]

    class FakeVerdict:
        def __init__(self, *, verdict, score):
            self.verdict = verdict
            self.score = score

    class FakeGraph:
        def __init__(self, *, root_nodes):
            captured["root_nodes"] = root_nodes

    class FakeMetric:
        score = 1.0
        reason = "The source and page match the retrieved chunk."

        def __init__(self, **kwargs):
            captured["metric_options"] = kwargs

        def measure(self, test_case):
            captured["test_case"] = test_case

    class FakeTestCase:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    metrics = ModuleType("deepeval.metrics")
    metrics.__path__ = []
    metrics.DAGMetric = FakeMetric
    dag = ModuleType("deepeval.metrics.dag")
    dag.BinaryJudgementNode = FakeNode
    dag.DeepAcyclicGraph = FakeGraph
    dag.VerdictNode = FakeVerdict
    test_case = ModuleType("deepeval.test_case")
    test_case.LLMTestCase = FakeTestCase
    test_case.SingleTurnParams = SimpleNamespace(
        ACTUAL_OUTPUT="actual_output",
        RETRIEVAL_CONTEXT="retrieval_context",
    )
    deepeval = ModuleType("deepeval")
    deepeval.__path__ = []
    monkeypatch.setitem(sys.modules, "deepeval", deepeval)
    monkeypatch.setitem(sys.modules, "deepeval.metrics", metrics)
    monkeypatch.setitem(sys.modules, "deepeval.metrics.dag", dag)
    monkeypatch.setitem(sys.modules, "deepeval.test_case", test_case)

    score, reason = citations.score_citation_accuracy(
        "What is required on roofs?",
        "Use edge protection.",
        [{"source_file": "roof-guide.pdf", "page_number": 4}],
        [{
            "text": "Use edge protection.",
            "source_file": "roof-guide.pdf",
            "page_number": 4,
            "section_heading": "Working at height",
        }],
        model="gpt-4.1",
    )

    assert score == 1.0
    assert "match" in reason
    assert [(verdict.verdict, verdict.score) for verdict in captured["verdicts"]] == [
        (True, 10),
        (False, 0),
    ]
    assert captured["metric_options"]["threshold"] == 1.0
    assert captured["metric_options"]["model"] == "gpt-4.1"
    assert '"source_file": "roof-guide.pdf"' in captured["test_case"].actual_output
    assert '"page_number": 4' in captured["test_case"].retrieval_context[0]


@pytest.mark.parametrize("score", [None, float("nan"), -0.1, 1.1, True])
def test_dag_scorer_rejects_invalid_metric_scores(monkeypatch, score):
    from src.evaluation import citations

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    class FakeNode:
        def __init__(self, **kwargs):
            pass

    class FakeVerdict:
        def __init__(self, **kwargs):
            pass

    class FakeGraph:
        def __init__(self, **kwargs):
            pass

    class FakeMetric:
        reason = ""

        def __init__(self, **kwargs):
            self.score = score

        def measure(self, test_case):
            pass

    metrics = ModuleType("deepeval.metrics")
    metrics.__path__ = []
    metrics.DAGMetric = FakeMetric
    dag = ModuleType("deepeval.metrics.dag")
    dag.BinaryJudgementNode = FakeNode
    dag.DeepAcyclicGraph = FakeGraph
    dag.VerdictNode = FakeVerdict
    test_case = ModuleType("deepeval.test_case")
    test_case.LLMTestCase = lambda **kwargs: SimpleNamespace(**kwargs)
    test_case.SingleTurnParams = SimpleNamespace(
        ACTUAL_OUTPUT="actual_output",
        RETRIEVAL_CONTEXT="retrieval_context",
    )
    deepeval = ModuleType("deepeval")
    deepeval.__path__ = []
    monkeypatch.setitem(sys.modules, "deepeval", deepeval)
    monkeypatch.setitem(sys.modules, "deepeval.metrics", metrics)
    monkeypatch.setitem(sys.modules, "deepeval.metrics.dag", dag)
    monkeypatch.setitem(sys.modules, "deepeval.test_case", test_case)

    with pytest.raises(RuntimeError, match="invalid citation score"):
        citations.score_citation_accuracy("Q", "A", [], [], model="gpt-4.1")
