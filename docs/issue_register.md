# US-08 issue register

Failures from the latest live notebook run require an owner and retest.

| Test ID | Observation | Owner | Status |
|---|---|---|---|
| None | No failures in the latest live run | - | Closed |

# Sprint 3 issue register

| ID | Observation | Owner | Status |
|---|---|---|---|
| S3-01 | Query latency ~32s against the 5s target. Retrieval is 0.79s; the rest is the `gpt-5-mini` generation call at the default reasoning effort. `reasoning_effort="minimal"` cuts it to 11.7s, `gpt-4.1-mini` to 7.1s. Any model change needs the edge case set re-run and H&S lead sign-off. See `startup_and_query_timings.md`. | TBC — sprint 5 | Open |
| S3-02 | Scope detection is a hardcoded keyword allowlist in `_preflight_guardrail_answer`. Widened in sprint 3 to cover construction vocabulary (it was refusing "what edge protection do I need on a roof?"), but a question phrased without a listed keyword is still refused. Needs a better mechanism. | TBC — sprint 4 | Open |
