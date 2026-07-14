# src/ingestion

The document pipeline: load the PDFs from `data/raw`, strip out boilerplate
(headers, footers, page numbers), and split the clean text into chunks with
metadata (document title, page number, industry category).
