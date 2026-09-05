# tests/eval

AI evaluation cases run with DeepEval, plus the golden (known-answer) question
and answer pairs used to check the chatbot's quality. The US-08 guardrail fixture
is `edge_case_questions.json`; run
`notebooks/US08_edge_case_prompt_testing.ipynb` to execute it.

This is where the five evaluation metrics (Faithfulness, Answer Relevancy,
Contextual Relevancy, helpfulness/plain-language, and citation accuracy) are
measured.
