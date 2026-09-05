"""Offline checks for the committed US-08 fixture and guardrail evaluator."""

import json
from pathlib import Path

from src.evaluation.edge_cases import evaluate_edge_case, validate_case_ids


FIXTURE = Path(__file__).with_name("edge_case_questions.json")


def _cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_edge_case_fixture_contains_all_25_cases():
    assert validate_case_ids(_cases()) == []


def test_evaluator_rejects_an_off_topic_answer():
    case = {"id": "OT-01", "category": "off_topic"}
    result = evaluate_edge_case(case, {"answer": "The capital of France is Paris.", "status": "ok"})
    assert result["status"] == "Fail"


def test_evaluator_accepts_a_legal_refusal():
    case = {"id": "LA-01", "category": "legal_advice"}
    result = evaluate_edge_case(
        case,
        {
            "answer": "I cannot provide legal advice. You may wish to seek advice from a qualified legal professional.",
            "status": "ok",
        },
    )
    assert result["status"] == "Pass"


def test_evaluator_rejects_an_unsupported_missing_corpus_answer():
    case = {"id": "NC-01", "category": "missing_corpus"}
    result = evaluate_edge_case(case, {"answer": "ISO 45001 clause 9.3 requires a management review.", "status": "ok"})
    assert result["status"] == "Fail"


def test_evaluator_accepts_general_boundary_guidance():
    case = {"id": "BC-03", "category": "boundary"}
    result = evaluate_edge_case(
        case,
        {"answer": "Record the hazard, raise it with the person in control, and follow the site's reporting process.", "status": "ok"},
    )
    assert result["status"] == "Pass"
