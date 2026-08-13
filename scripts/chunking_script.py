import json
from collections import defaultdict

from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_document(
    input_file,
    output_file,
    chunk_size=4000,
    chunk_overlap=800,
):
    """
    Reconstruct sections from a cleaned JSON file and
    chunk them using LangChain's RecursiveCharacterTextSplitter.

    Parameters
    ----------
    input_file : str
        Path to cleaned JSON file.
    output_file : str
        Path to save chunked JSON output.
    chunk_size : int, optional
        Maximum chunk size.
    chunk_overlap : int, optional
        Number of overlapping characters between chunks.

    Returns
    -------
    list
        List of chunk dictionaries.
    """

    # Load data
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Total records: {len(data)}")

    # Group by source file and section heading
    grouped_sections = defaultdict(list)

    for item in data:
        key = (
            item["source_file"],
            item["section_heading"],
        )

        grouped_sections[key].append(item)

    print(f"Sections found: {len(grouped_sections)}")

    # Reconstruct sections
    reconstructed_sections = []

    for (source_file, section_heading), items in grouped_sections.items():

        combined_text = " ".join(
            item["text"].strip()
            for item in items
            if item["text"].strip()
        )

        page_numbers = sorted(
            set(item["page_number"] for item in items)
        )

        reconstructed_sections.append(
            {
                "source_file": source_file,
                "section_heading": section_heading,
                "page_numbers": page_numbers,
                "text": combined_text,
            }
        )

    print(f"Reconstructed sections: {len(reconstructed_sections)}")

    # Create text splitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n",
            "\n",
            ". ",
            " ",
        ],
    )

    # Create chunks
    chunked_output = []
    chunk_counter = 1

    for section in reconstructed_sections:

        chunks = splitter.split_text(section["text"])

        for chunk in chunks:

            chunked_output.append(
                {
                    "chunk_id": f"CHUNK_{chunk_counter:05}",
                    "text": chunk,
                    "source_file": section["source_file"],
                    "page_number": min(section["page_numbers"]),
                    "section_heading": section["section_heading"],
                }
            )

            chunk_counter += 1

    print(f"Chunks created: {len(chunked_output)}")

    # Save output
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            chunked_output,
            f,
            indent=4,
            ensure_ascii=False,
        )

    print("Saved successfully")

    return chunked_output


def validate_chunks(chunked_output):
    """
    Run validation checks on chunk output.
    """

    required_fields = [
        "text",
        "source_file",
        "page_number",
    ]

    for chunk in chunked_output:
        for field in required_fields:
            assert field in chunk

    print("Required fields present")

    empty_chunks = [
        c for c in chunked_output
        if not c["text"].strip()
    ]

    print(f"Empty chunks: {len(empty_chunks)}")

    ids = [c["chunk_id"] for c in chunked_output]

    assert len(ids) == len(set(ids))

    print("Chunk IDs unique")

    lengths = [
        len(chunk["text"].split())
        for chunk in chunked_output
    ]

    print("Minimum words:", min(lengths))
    print("Maximum words:", max(lengths))
    print("Average words:", sum(lengths) / len(lengths))

    return {
        "total_chunks": len(chunked_output),
        "empty_chunks": len(empty_chunks),
        "minimum_words": min(lengths),
        "maximum_words": max(lengths),
        "average_words": sum(lengths) / len(lengths),
    }


if __name__ == "__main__":

    chunks = chunk_document(
        input_file="PCBUs-Working-Together-CLEANED.json",
        output_file="PCBUs-Working-Together-CHUNKED.json",
    )

    validate_chunks(chunks)