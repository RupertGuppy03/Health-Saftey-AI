# Cold start and warm query timings

Sprint 3, story 2. Recorded for the deployment phase: the cold start number sets
the readiness delay a container orchestrator has to allow for, and the warm query
number is the one to compare against the project's 5 second response target.

Before this story, all three clients (the ChromaDB client, the OpenAI embedding
client and the chat model) were rebuilt on every request, so there was no warm
path — every question paid the cold cost. They are now opened once at startup.

## How to measure

1. Start the backend from a cold process: `./scripts/run_api.sh`
2. **Cold start** — call `GET /health` and read `startup_seconds`. This is the
   time spent opening the vector store and constructing the model clients, before
   any question is asked.
3. **First query** — ask a question through `POST /chat` and read
   `latency_seconds`.
4. **Warm query** — ask the *same* question again and read `latency_seconds`.
   Same question so retrieval does the same work, and the difference is
   initialisation rather than a different amount of retrieved text.

Use a question that clears the scope guardrail, e.g.
*"What edge protection do I need for work at height?"*

## Results

Measurement: Cold start (`startup_seconds`) = 0.71 + 0.56 + 0.69 / 3 = 0.65
Seconds: First query (`latency_seconds`) = 34.28
Notes: Warm query (`latency_seconds`) = 33.05



- **Date measured:** 8/9/26
- **Machine:** Macbook Air: M1 chip
- **Collection:** `hs_construction_v1`, 3,646 chunks
- **Models:** `text-embedding-3-small` (query embedding), `gpt-5-mini` (answer)

## Notes

<!-- Anything that skewed a number: cold OS file cache, network, a slow API call. -->

---

# Conversation history cost

Sprint 3, story 10. What sending the conversation with a question costs, recorded
because the Definition of Done asks for the history limit's token cost impact.

## Where the cost falls

A follow-up pays in three places; a first question pays in none of them, because
with no history the rewrite is skipped and the prompt is unchanged.

| | What is sent | Paid when |
|---|---|---|
| The rewrite call | System prompt + the trimmed conversation + the question | Only when history is present |
| The answering prompt | The trimmed conversation, as messages before the question | Only when history is present |
| The request body | The trimmed conversation as JSON | Only when history is present |

Retrieval is unaffected: it embeds one rewritten question, the same as before.

`HISTORY_TOKEN_LIMIT` (16,000) is the ceiling on all three at once, so the worst
case is bounded no matter how long a conversation runs. A typical exchange in this
app is roughly 200–400 tokens, which puts the ceiling at roughly 60–80 exchanges.

## How to measure

Run `notebooks/S3_US10_followup_history.ipynb`. Section 5 prints the conversation's
token count and the mean latency of the same 25 questions with and without history,
and the difference between them is the rewrite's cost.

For a per-question figure, ask a question through `POST /chat` with no `history`,
then ask a follow-up with it, and compare `latency_seconds`.

## Results

<!-- Fill in from section 5 of the notebook. -->

- **Date measured:** 15/9/26
- **Machine:** Ruperts macbook air m1
- **Tokens in the test conversation:** 32
- **Mean latency, all 25 cases (without -> with history):** 4.13s -> 4.33s (+0.20s)
- **Mean latency, cases that actually answered (without -> with):** 22.83s -> 24.94s (+2.11s)
- **Rewrite cost per follow-up:** ~0.2-2s, against a ~23s answer
- **Rewrite model / effort:** `gpt-5-mini` / `minimal`

The two figures differ because the all-cases mean is dominated by guardrail
refusals that return in well under a second. The cases that reach the language
model are the honest picture of what a user waits for, and there the rewrite is
roughly 8% on top of an answer — not the doubling that running it at the
answering model's default effort would have cost.

## Notes

The rewrite runs at `minimal` reasoning effort deliberately. At the answering
model's default effort a rewrite would cost roughly what an answer costs (~32s,
issue S3-01), which would double the wait on every follow-up for what is a
mechanical edit. Both the model and the effort are settings — see
`HISTORY_CONDENSE_MODEL` and `HISTORY_CONDENSE_REASONING_EFFORT`.
