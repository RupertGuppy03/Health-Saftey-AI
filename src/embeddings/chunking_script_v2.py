import json
from collections import defaultdict

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer


# =====================================================
# SPRINT 1 - CHUNKING
# =====================================================

def chunk_document(
    input_file,
    output_file,
    chunk_size=4000,
    chunk_overlap=800,
):
    """
    Reconstruct sections from cleaned JSON
    and generate chunks.
    """

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Total records: {len(data)}")

    grouped_sections = defaultdict(list)

    for item in data:
        key = (
            item["source_file"],
            item["section_heading"],
        )
        grouped_sections[key].append(item)

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

        section_data = {
            "source_file": source_file,
            "section_heading": section_heading,
            "page_numbers": page_numbers,
            "text": combined_text,
        }

        # Preserve chunk_type if source data contains it
        chunk_types = {
            item.get("chunk_type")
            for item in items
            if item.get("chunk_type")
        }

        if len(chunk_types) == 1:
            section_data["chunk_type"] = list(chunk_types)[0]

        reconstructed_sections.append(section_data)

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

    chunked_output = []
    chunk_counter = 1

    for section in reconstructed_sections:

        chunks = splitter.split_text(section["text"])

        for chunk in chunks:

            chunk_record = {
                "chunk_id": f"CHUNK_{chunk_counter:05}",
                "text": chunk,
                "source_file": section["source_file"],
                "page_number": min(section["page_numbers"]),
                "section_heading": section["section_heading"],
            }

            if "chunk_type" in section:
                chunk_record["chunk_type"] = section["chunk_type"]

            chunked_output.append(chunk_record)

            chunk_counter += 1

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            chunked_output,
            f,
            indent=4,
            ensure_ascii=False,
        )

    print(f"Chunks created: {len(chunked_output)}")
    print("Saved successfully")

    return chunked_output


# =====================================================
# VALIDATION
# =====================================================

def validate_chunks(chunked_output):

    required_fields = [
        "text",
        "source_file",
        "page_number",
        "section_heading",
    ]

    for chunk in chunked_output:
        for field in required_fields:

            if field not in chunk:
                raise ValueError(
                    f"Missing field '{field}' "
                    f"for chunk {chunk.get('chunk_id')}"
                )

            value = chunk[field]

            if value is None:
                raise ValueError(
                    f"Null value for '{field}' "
                    f"on chunk {chunk.get('chunk_id')}"
                )

            if isinstance(value, str) and not value.strip():
                raise ValueError(
                    f"Empty value for '{field}' "
                    f"on chunk {chunk.get('chunk_id')}"
                )

    print("Chunk validation successful")


# =====================================================
# SPRINT 2 - CHROMADB INGESTION
# =====================================================

def ingest_to_chromadb(
    chunk_file,
    collection_name="document_chunks",
    chroma_path="./chroma_db",
    embedding_model="all-MiniLM-L6-v2",
):

    print("Loading chunk file...")

    with open(chunk_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    validate_chunks(chunks)

    print("Loading embedding model...")
    model = SentenceTransformer(embedding_model)

    print("Generating embeddings...")

    texts = [
        chunk["text"]
        for chunk in chunks
    ]

    embeddings = model.encode(
        texts,
        show_progress_bar=True
    ).tolist()

    client = chromadb.PersistentClient