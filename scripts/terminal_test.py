import time

from src.answer import answer_question
from src.retrieval import retriever

question = input("Enter your question: ")

start_time = time.time()

result = answer_question(question)

end_time = time.time()

print("\nANSWER")
print("--------------------")
print(result["answer"])

chunks = retriever.retrieve(question)

print("\nRETRIEVED CHUNKS")
print("--------------------")
print(retriever.format_results(chunks))

latency = end_time - start_time

print("\nRESPONSE LATENCY")
print("--------------------")
print(f"{latency:.2f} seconds")