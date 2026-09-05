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
