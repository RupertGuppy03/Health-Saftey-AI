# tests/eval

AI evaluation cases run with DeepEval, plus the golden (known-answer) question
and answer pairs used to check the chatbot's quality. The US-08 guardrail fixture
is `edge_case_questions.json`; run
`notebooks/US08_Sprint2_edge_case_prompt_testing.ipynb` to execute it.

This is where the five evaluation metrics (Faithfulness, Answer Relevancy,
Contextual Relevancy, helpfulness/plain-language, and citation accuracy) are
measured.

Run `notebooks/S4_contextual_relevancy_eval.ipynb` to retrieve chunks for the
golden questions and score their relevance to each question with DeepEval. The
notebook writes per-question scores, reasons, and the mean score to
`contextual_relevancy_results.md`. It needs the persisted ChromaDB in
`vectorstore/` and an OpenAI API key in `.env` (`OPEN_AI_API_KEY` or
`OPENAI_API_KEY`). A score at or above 0.9 meets the project target.
