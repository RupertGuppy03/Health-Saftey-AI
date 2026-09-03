# scripts

One-command runners for common jobs — for example, ingesting all the documents
end-to-end or running the full evaluation suite. Handy shortcuts so nobody has
to remember a long sequence of steps.


## Terminal Test 

To run the terminal test script, run this command from the project root:

```bash
python -m scripts.terminal_test

```
Enter a question when prompted.
The script will display:
The generated answer
Retrieved chunks
Source file
Page number
Section heading
Response latency in seconds