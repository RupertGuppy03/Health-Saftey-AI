
# US-06: How to run the Retrieval-to-GPT-4o flow

This guide explains how to run the US-06 answer chain, test it with a question, and inspect the answer and source metadata it returns.

## What this feature does

The US-06 flow does the following:

- retrieves the most relevant document chunks from ChromaDB
- formats the returned chunk text as prompt context
- sends the question and context to GPT-4o through LangChain
- returns:
  - the generated answer
  - the source documents and sections used
  - a graceful "no results" or API error response when applicable

## Files involved

- `src/answer.py` — main answer chain implementation
- `src/retrieval/retriever.py` — retrieval logic for ChromaDB
- `src/config/prompts.py` — grounding system prompt
- `notebooks/US06_retrieval_to_gpt4o_langchain.ipynb` — notebook demo

## 1) Prerequisites

From the project root:

```bash
cd /Users/jerseyleigh/Documents/GitHub/Health-Saftey-AI.worktrees/connect-retrieval-to-gpt4o-langchain
python3 -m pip install -r requirements.txt
```

Make sure your environment file contains an OpenAI key. The project accepts either of these names:

```env
OPENAI_API_KEY=your_key_here
```

or

```env
OPEN_AI_API_KEY=your_key_here
```

If you use a `.env`, keep it in the project root so the app can load it automatically.


## 2) Run a single test question in Python

If you want to test one question directly from the terminal, use:

```bash
cd /Users/jerseyleigh/Documents/GitHub/Health-Saftey-AI.worktrees/connect-retrieval-to-gpt4o-langchain
python3 - <<'PY'
from src.answer import answer_question

question = "What edge protection do I need when working on a roof?"

result = answer_question(question)
print(result)
PY

#Single line:
python3 -c 'from src.answer import answer_question; result = answer_question("What edge protection do I need when working on a roof?"); print(result)'
```



This will return a dictionary shaped roughly like:

```python
{
    "answer": "Use edge protection and guardrails...",
    "sources": [
        {
            "source_file": "working-on-roofs.pdf",
            "page_number": 4,
            "section_heading": "Working at height",
            "chunk_id": "roof-1"
        }
    ],
    "status": "ok"
}
```

## 4) Try a no-results question

This checks the graceful fallback when retrieval finds nothing:

```bash
cd /Users/jerseyleigh/Documents/GitHub/Health-Saftey-AI.worktrees/connect-retrieval-to-gpt4o-langchain
python3 - <<'PY'
from src.answer import answer_question

result = answer_question("What is the capital of France?")
print(result)
PY
```

Expected response:

```python
{
    "answer": "No relevant information was found for that question in the available documents.",
    "sources": [],
    "status": "no_results"
}
```

## 5) Try an API failure check

You can simulate a failing LLM by injecting a stub, or use the notebook's error example.

Example:

```bash
cd /Users/jerseyleigh/Documents/GitHub/Health-Saftey-AI.worktrees/connect-retrieval-to-gpt4o-langchain
python3 - <<'PY'
from src.answer import answer_question

class FailingLLM:
    def invoke(self, payload):
        raise RuntimeError("quota exceeded")

question = "What edge protection do I need when working on a roof?"
result = answer_question(
    question,
    retriever_fn=lambda q, n_results=None, collection_name=None: [
        {
            "chunk_id": "roof-1",
            "source_file": "working-on-roofs.pdf",
            "page_number": 4,
            "section_heading": "Working at height",
            "text": "Roof work requires edge protection and guardrails."
        }
    ],
    llm=FailingLLM(),
)
print(result)
PY
```

Expected response:

```python
{
    "answer": "I could not generate an answer because the language model is currently unavailable.",
    "sources": [],
    "status": "error",
    "error": "OpenAI API error: quota exceeded"
}
```

## 6) Check the source metadata

The answer should include the source information that came from ChromaDB. For each retrieved chunk, the metadata should include:

- `source_file`
- `page_number`
- `section_heading`
- `chunk_id`

This matters for attribution, and the acceptance tests for US-06 check that these are returned with the answer.

## 7) Manual verification checklist

Use this checklist when testing with real PDFs:

- [ ] Run a question that should match a real document section
- [ ] Confirm the generated answer is grounded in the retrieved chunk text
- [ ] Confirm the answer includes the correct `source_file` and `page_number`
- [ ] Confirm the `section_heading` matches the source PDF section
- [ ] Confirm a no-result query returns the graceful message instead of a fabricated answer
- [ ] Confirm an OpenAI failure is reported without crashing the script

## 8) Common issues

If you see an error like:

```text
No OpenAI API key found. Set OPEN_AI_API_KEY (or OPENAI_API_KEY) in your .env file.
```

then add your key to `.env` in the project root.

If you see a vector store error, make sure the Chroma collection has been created and populated for the project. If not, the notebook will fall back to the demo payload so you can still test the flow.

## 9) Quick summary

The simplest way to run US-06 is:

1. open the notebook
2. run the cells
3. change the `question` value to any real work-safety question
4. inspect the returned `answer` and `sources`

That is the fastest way to see the full retrieval-to-GPT-4o pipeline in action.
