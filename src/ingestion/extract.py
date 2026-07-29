"""Reproducible PDF extraction via the Unstructured.io Jobs / Transform API.

This is the first step of the ingestion pipeline: raw PDF -> raw Unstructured JSON.
That JSON is the source of truth the deterministic cleaner (`clean.py`) runs on, so
this script's only job is to reproduce the exact API call that produced it.

It mirrors the notebook cell that generated the committed pcbus JSON:
  * Jobs / Transform API on `platform-api.transform.unstructured.io` (NOT the
    Serverless Partition API — a different Unstructured product).
  * A VLM partitioner (best table/layout fidelity), submitted as a job.
  * create job -> poll until COMPLETED -> download each output -> save as JSON.

Every saved file is named `{file_id}.json` (the file_id already ends in `.pdf`), so
the output matches the `*.pdf.json` shape that `clean.py._find_cached_json()` globs.

The API is paid and non-deterministic, so there is no pytest for this module — the
committed JSON is the cached artifact and cleaning is tested against that. Verify this
step by running it on a new document and confirming the JSON lands.

The API key is read from the environment (`UNSTRUCTURED_API_KEY` in .env, which is
gitignored) — never hard-coded, never committed.

Run:

    .venv/bin/python -m src.ingestion.extract \\
        --input-dir  data/raw/building_and_construction/<doc> \\
        --output-dir data/processed/<doc>
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from unstructured_client import UnstructuredClient
from unstructured_client.models.operations import CreateJobRequest
from unstructured_client.models.shared import (
    BodyCreateJob,
    InputFiles,
    JobInformation,
    JobStatus,
)

load_dotenv()

# The Transform API host. The VLM partitioner lives here, not on the Serverless
# Partition host — this is the product that produced our source-of-truth JSON.
TRANSFORM_SERVER_URL = "https://platform-api.transform.unstructured.io"

# The one-node job: a VLM partitioner. `is_dynamic`/`allow_fast` match the settings
# used to extract the demo document, so re-runs stay consistent with clean.py's input.
# `extract_image_block_types: []` stops the hi-res pages (which is_dynamic falls back
# to) from embedding base64 images — those were ~80% of the output size and are unused
# by clean.py (Image elements are dropped; tables keep their text_as_html).
PARTITIONER_JOB = {
    "job_nodes": [
        {
            "name": "Partitioner",
            "type": "partition",
            "subtype": "vlm",
            "settings": {
                "is_dynamic": True,
                "allow_fast": True,
                "extract_image_block_types": [],
            },
        }
    ]
}

# Seconds between job-status polls.
POLL_SECONDS = 10

# Per-read (gap) timeout for the streaming download. Unstructured streams the output
# slowly in chunks, so this is a tolerance for the gap BETWEEN chunks, not a total
# cap: a slow-but-steady trickle downloads fine, but a true stall (no bytes for this
# long) fails loudly instead of hanging forever.
DOWNLOAD_READ_TIMEOUT_S = 60

# How often to print a download-progress line.
PROGRESS_EVERY_S = 30


def _build_client() -> UnstructuredClient:
    """Return an authenticated client, or raise if the API key is missing.

    The server URL is fixed to the bare Transform host (where the Jobs/VLM API
    lives) and intentionally NOT read from the environment: the SDK appends its own
    path, so a stale UNSTRUCTURED_API_URL carrying a path suffix (e.g. ".../api/v1")
    makes every request 404. Pinning it here keeps runs reproducible across the team.
    """
    api_key = os.environ.get("UNSTRUCTURED_API_KEY")
    if not api_key:
        raise RuntimeError(
            "UNSTRUCTURED_API_KEY is not set. Add it to .env (which is gitignored)."
        )
    return UnstructuredClient(api_key_auth=api_key, server_url=TRANSFORM_SERVER_URL)


def _collect_pdfs(input_dir: Path) -> list[InputFiles]:
    """Wrap every *.pdf in `input_dir` as an Unstructured InputFiles upload."""
    input_files: list[InputFiles] = []
    for pdf in sorted(input_dir.glob("*.pdf")):
        content_type, _ = mimetypes.guess_type(pdf)
        input_files.append(
            InputFiles(
                content=pdf.read_bytes(),
                file_name=pdf.name,
                content_type=content_type or "application/octet-stream",
            )
        )
    return input_files


def extract_document(input_dir: Path | str, output_dir: Path | str) -> list[Path]:
    """Extract every PDF in `input_dir` to raw Unstructured JSON in `output_dir`.

    Submits one Transform job (VLM partitioner), polls it to completion, downloads
    each output node and writes it as `{file_id}.json`. Returns the saved paths.
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    input_files = _collect_pdfs(input_dir)
    if not input_files:
        raise FileNotFoundError(f"No PDF files found in {input_dir}")

    client = _build_client()

    # Step 1: create the job. `job_information` is Optional on the response, so
    # guard it before use rather than dereferencing a possibly-None value.
    print(f"Submitting {len(input_files)} file(s) from {input_dir}...")
    create = client.jobs.create_job(
        request=CreateJobRequest(
            body_create_job=BodyCreateJob(
                request_data=json.dumps(PARTITIONER_JOB),
                input_files=input_files,
            )
        )
    )
    if create.job_information is None:
        raise RuntimeError("create_job returned no job information")
    job_id = create.job_information.id
    print(f"Job ID: {job_id}")

    # Step 2: poll until the job finishes (compare against the JobStatus enum).
    job_info: JobInformation
    while True:
        poll = client.jobs.get_job(request={"job_id": job_id})
        if poll.job_information is None:
            raise RuntimeError("get_job returned no job information")
        job_info = poll.job_information
        status = job_info.status
        print(f"Job status: {status.value}")
        if status == JobStatus.COMPLETED:
            print("Job completed.")
            break
        if status in (JobStatus.FAILED, JobStatus.STOPPED):
            raise RuntimeError(f"Job failed: {status.value}")
        time.sleep(POLL_SECONDS)

    # Step 3: stream each output node to disk. (The SDK's download reads the whole
    # body at once with no timeout, which hangs on Unstructured's slow chunked
    # transfer; streaming shows progress and fails loudly on a real stall.)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for output_file in job_info.output_node_files or []:
        out_path = output_dir / f"{output_file.file_id}.json"
        _download_output(job_id, output_file.file_id, out_path)
        saved.append(out_path)

    return saved


def _download_output(job_id: str, file_id: str, out_path: Path) -> None:
    """Stream a job's output JSON to disk, printing progress every PROGRESS_EVERY_S.

    Uses a raw streaming GET rather than the SDK's download so a slow transfer shows
    progress instead of hanging silently. Afterwards the file is re-written indented
    for readability (the server sends minified, single-line JSON), which also confirms
    the download is complete and valid JSON.
    """
    api_key = os.environ["UNSTRUCTURED_API_KEY"]
    url = f"{TRANSFORM_SERVER_URL}/api/v1/jobs/{job_id}/download"
    timeout = httpx.Timeout(
        connect=30.0, read=DOWNLOAD_READ_TIMEOUT_S, write=30.0, pool=30.0
    )

    print("Downloading...")
    start = last = time.time()
    mb = 0.0
    with httpx.stream(
        "GET",
        url,
        params={"file_id": file_id},
        headers={"unstructured-api-key": api_key},
        timeout=timeout,
        follow_redirects=True,
    ) as response:
        response.raise_for_status()
        with open(out_path, "wb") as fh:
            for chunk in response.iter_bytes():
                fh.write(chunk)
                mb += len(chunk) / 1e6
                if time.time() - last >= PROGRESS_EVERY_S:
                    print(f"  {mb:.2f} MB   {time.time() - start:.0f}s elapsed")
                    last = time.time()

    out_path.write_text(
        json.dumps(json.loads(out_path.read_text()), indent=2, ensure_ascii=False)
    )
    print(f"Saved: {out_path} ({out_path.stat().st_size / 1e6:.2f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Folder of raw PDFs, e.g. data/raw/building_and_construction/<doc>",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Where to write the raw JSON, e.g. data/processed/<doc>",
    )
    args = parser.parse_args()
    extract_document(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
