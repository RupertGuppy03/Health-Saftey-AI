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
| S3-03 | Story 10 works around S3-02 for follow-ups rather than fixing it. The guardrail is now split: `_intent_refusal` (legal advice, external standards) still reads the user's own words, while `_scope_refusal` (the keyword allowlist) reads the rewritten standalone question, so "what about on a smaller one?" resolves instead of being refused. The allowlist itself is unchanged and a standalone question behaves exactly as before. **Residual risk:** a rewrite that invents health and safety wording could talk an off-topic question past the keyword check. The rewrite prompt is told to leave unrelated questions alone, and a question the corpus cannot support still returns `no_results` rather than an answer — but both are mitigations, not a fix. Closes with S3-02. | TBC — sprint 4 | Open |
| S3-04 | Every message is routed through retrieval, including ones that are operations on the conversation rather than questions about the corpus. "Summarise this" re-retrieves and summarises **newly retrieved chunks** instead of condensing the previous answer, so the content drifts to material the user never saw. Found in live browser testing 15/9/26 on an asbestos conversation. Story 10 narrows the symptom by rewriting such requests to name the subject, but the routing is the cause. **Fix: the planned agent harness**, where RAG becomes one tool among several (checklisting, document generation) and a router decides which handles a message. | TBC — agent harness | Open |
| S3-05 | Questions about the conversation itself ("what topics did we discuss?") are refused by the scope guardrail, because they contain no health and safety keyword and the rewrite correctly leaves them alone. The app holds the conversation and will not describe it. Low stakes, poor impression. Deliberately not worked around in story 10: rewriting it into a corpus question would answer from the documents rather than from the conversation, which is worse. **Fix: the planned agent harness** — same router as S3-04. | TBC — agent harness | Open |
