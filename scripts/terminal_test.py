import time

from src.answer import answer_question
from src.retrieval.retriever import FALLBACK_SECTION_HEADING, format_results

question = input("Enter your question: ")

start_time = time.time()

result = answer_question(question)

end_time = time.time()

print("\nANSWER")
print("--------------------")
print(result["answer"])

# The structured metadata the chain returned, not whatever the model happened to
# write in its answer text.
print("\nSOURCES")
print("--------------------")

sources = result.get("sources", [])

if not sources:
    print("  No sources.")
else:
    for source in sources:
        heading = source["section_heading"] or FALLBACK_SECTION_HEADING
        print(f"  {source['source_file']} | page {source['page_number']} | {heading}")

# The chunks the answer was actually built from — answer_question hands them
# back, so there is no second retrieval (and no second embedding call) here.
print("\nRETRIEVED CHUNKS")
print("--------------------")
print(format_results(result.get("chunks", [])))

latency = end_time - start_time

print("\nRESPONSE LATENCY")
print("--------------------")
print(f"{latency:.2f} seconds")
