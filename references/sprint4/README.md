# Sprint 4 — Hazard detection & scope handling

Planning docs and user stories for this sprint. Goal: hazard detection and
mitigation, out-of-scope query handling, and construction document tagging. See
[`../Project_User_Stories.md`](../Project_User_Stories.md).

---

## 1. Set Up the Latency and Quality Testing Notebook

**MoSCoW:** Must | **Est:** 1–2 days

As a developer, I want one notebook that measures latency and answer quality in the same run so that every configuration we try is judged on speed and quality together.

**Tasks**
- Create a notebook that takes a model, a reasoning effort and a verbosity level for each run
- Include the candidate models: `gpt-5-mini` (current), `gpt-5.4-mini` and `gpt-5.4-nano`
- For each run, record the latency and score the answer with G-Eval
- Use 3 questions from the golden set, the same for every run
- Include the current configuration as the baseline that every other run is compared against

**Acceptance Tests**
- Given a model, reasoning effort and verbosity level, when the notebook is run, then a latency and a G-Eval score are recorded for each question.
- Given two configurations, when their results are compared, then both answered the same questions.
- Given the current configuration, when the notebook is run, then its results are recorded as the baseline.

**Definition of Done**
- A different setting can be tested by changing its values, with no code edits
- Another team member can run the notebook from a clean clone

---

## 2. Run the Tests and Record the Results

**MoSCoW:** Must | **Est:** 1–2 days

As a team, we want every configuration from the notebook tested from the question bank and the results laid out side by side so that we pick a faster setup on evidence instead of trading away answer quality without noticing.

**Tasks**
- Run each model at the reasoning effort levels it supports
- Run each model at `low` and `medium` verbosity
- Cross-tabulate the results by model, reasoning effort and verbosity, showing median latency and G-Eval score for each
- Flag any configuration whose G-Eval score falls below the baseline
- Record the recommended configuration and why it was chosen

**Acceptance Tests**
- Given every configuration, when the table is built, then each one shows both a median latency and a G-Eval score.
- Given a configuration that scores below the baseline, when the table is read, then it is visibly flagged.
- Given the table, when the fastest configuration that holds the baseline is looked for, then it can be identified without re-running anything.

**Definition of Done**
- Results are committed to the repo so the comparison can be reviewed later
- The recommendation is reviewed with the H&S lead before story 3 starts

---

## 3. Apply the Chosen Model and Settings

**MoSCoW:** Must | **Est:** 1 day

As a user, I want the assistant running on the fastest configuration that keeps answer quality so that I wait less for a trustworthy answer.

**Tasks**
- Update the model, reasoning effort and verbosity in `settings.py` to the configuration chosen in story 2
- Re-run the edge case set and the follow-up tests on the new configuration
- Re-record the query latency in `docs/startup_and_query_timings.md`
- Update issue S3-01 in the issue register with the outcome

**Acceptance Tests**
- Given the new settings, when a question is asked through the interface, then the wait before the answer begins is shorter than the baseline.
- Given the new settings, when the edge case set is re-run, then the guardrails behave as they did in earlier testing.
- Given the settings need changing later, when they are changed, then only `settings.py` is edited.

**Definition of Done**
- H&S lead sign-off recorded before the change is merged, as S3-01 requires
- No model name, reasoning effort or verbosity value is hardcoded outside `settings.py`


