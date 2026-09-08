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
