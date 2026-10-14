# tests/eval

AI evaluation cases run with DeepEval, plus the golden (known-answer) question
and answer pairs used to check the chatbot's quality. The US-08 guardrail fixture
is `edge_case_questions.json`; run
`notebooks/US08_Sprint2_edge_case_prompt_testing.ipynb` to execute it.

This is where the five evaluation metrics (Faithfulness, Answer Relevancy,
Contextual Relevancy, helpfulness/plain-language, and citation accuracy) are
measured.

## Citation presence and DAG score

Run `notebooks/S4_faithfulness_eval.ipynb` from top to bottom to generate live
answers for its golden questions, score faithfulness, and run the citation DAG
evaluation in section 8. That section prints whether each answer returned a
source citation and its DeepEval `DAGMetric` score, pass/fail result, and reason.
The DAG checks that cited source files and page numbers match the retrieved
chunks. Missing citations are reported as absent and fail the citation check.

The notebook calls the answering pipeline and an LLM judge, so it needs a
populated local vector store and an OpenAI API key. These judge calls add latency
and API cost. The same DAG citation scorer runs for each grounded live chat
answer on the backend. The offline pytest tests mock DeepEval and make no API
calls.
