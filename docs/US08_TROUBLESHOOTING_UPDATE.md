# US-08 troubleshooting update — live run 1

This is an additive record for the first live notebook run. It does not replace the
original US-08 change summary.

## Result recorded

The live run passed **18/25** cases. The following seven cases failed:

- OT-01, OT-02, OT-03, OT-04
- NC-02, NC-03, NC-04

The original detailed results remain in
[`docs/edge_case_test_results.md`](../docs/edge_case_test_results.md).

## Diagnosis

### OT-01 to OT-04

These questions returned:

> No relevant information found in the available documents.

They did not reach the system prompt because `answer_question()` returned a hard-coded
no-results response as soon as retrieval returned no chunks. The prompt therefore had no
opportunity to produce the required off-topic redirect.

### NC-02 to NC-04

These questions concern workplace health and safety, but refer to Australian, OSHA, or
Singapore rules. The system treated them as ordinary off-topic questions and returned the
redirect instead of identifying that the information was unavailable in the New Zealand
knowledge base.

## Changes made

### `src/answer.py`

Added `_no_context_answer(question)`. When retrieval returns no usable context, it now:

- Returns the off-topic redirect when the question has no workplace health and safety
  signal.
- Returns the unavailable-information response when the question contains safety-related
  terms but the corpus has no relevant information.

This fixes the immediate no-results path without requiring an unnecessary second LLM call.

### `src/config/prompts.py`

Added an explicit rule that foreign workplace-safety questions and external standards such
as ISO, OSHA, Australian WHS, and Singapore rules are safety-related but unavailable from
the New Zealand knowledge base.

### `tests/test_answer_chain.py`

Updated the no-results expectation to match the new off-topic redirect behaviour.

### Documentation

The first run and diagnosis were appended to:

- [`docs/edge_case_test_results.md`](../docs/edge_case_test_results.md)
- [`docs/prompt_iteration_log.md`](../docs/prompt_iteration_log.md)
- [`docs/issue_register.md`](../docs/issue_register.md)

## Retest status

The seven cases remain open until the live notebook is run again. After rerunning,
update the historical result rather than deleting the 18/25 record.

| Test IDs | Status before | Status after |
|---|---|---|
| OT-01, OT-02, OT-03, OT-04 | Fail | Pending live retest |
| NC-02, NC-03, NC-04 | Fail | Pending live retest |

An owner still needs to be assigned in the issue register before the story is complete.
