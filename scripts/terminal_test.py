from src.pipeline import run_query
from src.retrieval.retriever import FALLBACK_SECTION_HEADING, format_results

question = input("Enter your question: ")

# run_query times the pipeline itself, so the same latency the API reports is
# the one printed here.
result = run_query(question)

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

# The chunks the answer was actually built from — run_query hands them back, so
# there is no second retrieval (and no second embedding call) here.
print("\nRETRIEVED CHUNKS")
print("--------------------")
print(format_results(result.get("chunks", [])))

print("\nRESPONSE LATENCY")
print("--------------------")
print(f"{result['latency_seconds']:.2f} seconds")
