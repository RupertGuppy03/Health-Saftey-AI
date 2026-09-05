# US-08 prompt iteration log

Record each failed live case here before changing the system prompt. Keep the actual
response in `edge_case_test_results.md` so the change can be reviewed and retested.

## Iteration template

### Test ID

<!-- Example: NC-01 -->

### Failure description

<!-- What differed from the expected behaviour? -->

### Root cause

<!-- Check retrieval, chunk quality, system prompt, then chunk size. -->

### Prompt change

<!-- Quote the small prompt change made in src/config/prompts.py. -->

### Retest result

| Test ID | Status before | Status after |
|---|---|---|
| <!-- ID --> | <!-- Pass/Fail --> | <!-- Pass/Fail --> |

### Owner

<!-- Required if the case remains failed. -->

---

## Iteration 1 — 18/25 live cases passed

### Test IDs

OT-01, OT-02, OT-03, OT-04, NC-02, NC-03, NC-04

### Failure description

OT-01 through OT-04 returned `No relevant information found in the available
documents.` instead of redirecting the user. NC-02 through NC-04 returned the
off-topic redirect even though they were workplace health and safety questions about
non-New Zealand rules.

### Root cause

Two issues were identified:

1. `src/answer.py` returned a hard-coded no-results response before the system prompt
   could classify an off-topic question.
2. The prompt did not explicitly distinguish foreign or external safety standards from
   ordinary off-topic questions.

### Prompt and pipeline change

`src/config/prompts.py` now states that foreign workplace-safety questions and ISO, OSHA,
Australian WHS, and Singapore rules are safety-related but unavailable from the New Zealand
knowledge base. `src/answer.py` now selects a redirect for questions with no workplace
health and safety signal and an unavailable-information response for safety-related
questions with no retrieved context.

### Retest result

| Test IDs | Status before | Status after |
|---|---|---|
| OT-01, OT-02, OT-03, OT-04 | Fail | Pending live retest |
| NC-02, NC-03, NC-04 | Fail | Pending live retest |

### Owner

TBD — assign an owner before closing the issue register entries.

---

## Iteration 3 — 23/25 live cases passed

### Test IDs

LA-02 and LA-03

### Failure description

LA-02 received the off-topic redirect instead of a legal-advice refusal. LA-03 received
the same redirect instead of refusing compensation advice.

### Root cause

The preflight guardrail checked external scope and generic workplace-health signals, but
did not recognize all legal-intent phrases. “Employment law case” did not match the
generic workplace signal, while “compensation” was not classified as a legal request.

### Prompt and pipeline change

Added a legal-intent check before all other preflight scope checks in `src/answer.py`.
It covers legal, law, lawyer, court, compensation, claim, dispute, sue, and employment-law
phrasing and returns the standard legal refusal without retrieval.

### Retest result

| Test IDs | Status before | Status after |
|---|---|---|
| LA-02, LA-03 | Fail | Pending live retest |

### Owner

TBD — assign an owner before closing the issue register entries.

---

## Iteration 2 — second live run remained at 18/25

### Test IDs

OT-01, OT-02, OT-03, OT-04, NC-02, NC-03, NC-04

### Failure description

The same seven cases failed after the first fallback and prompt changes. The OT cases
still returned the old no-results response, and the NC cases were redirected as ordinary
off-topic questions.

### Root cause

The notebook likely reused cached Python modules, so it did not load the updated
`src.answer` fallback. Separately, retrieval returned plausible New Zealand context for
foreign-regulation questions, allowing the model to make the wrong scope decision.

### Prompt and pipeline change

Added `_preflight_guardrail_answer()` in `src/answer.py` to handle unambiguous scope cases
before retrieval. The notebook now reloads `src.config.prompts` and `src.answer` before
running the cases.

### Retest result

| Test IDs | Status before | Status after |
|---|---|---|
| OT-01, OT-02, OT-03, OT-04 | Fail | Pending live retest |
| NC-02, NC-03, NC-04 | Fail | Pending live retest |

### Owner

TBD — assign an owner before closing the issue register entries.
