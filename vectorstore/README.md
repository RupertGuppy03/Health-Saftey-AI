# vectorstore

The persisted ChromaDB vector store — the embedded document chunks the chatbot
searches at query time.

The contents of this folder are **not committed**. Chroma rewrites
`chroma.sqlite3` just from opening the collection, so tracking it directly would
leave everyone with a permanently modified 46MB binary that git cannot merge.
This README is kept so the folder still exists after you clone.

Instead the team shares one identical store as a committed snapshot,
`vectorstore-snapshot.tar.gz` in the repository root.

## Restoring the shared store

Close any Jupyter kernel that has opened the store first, then activate the venv
— `source .venv/bin/activate` on macOS/Linux, `.venv\Scripts\activate` on
Windows — and run this from the repo root. The commands themselves are the same
on every platform:

```bash
git clean -xfd vectorstore/
tar -xzf vectorstore-snapshot.tar.gz -C vectorstore
python scripts/check_chroma_collection.py
```

`git clean -xfd` deletes the ignored contents of the folder but keeps this
README, which is tracked. Wiping first matters: your old collection lives under
a differently-named UUID folder that nothing will reference afterwards, and a
stale `chroma.sqlite3-wal` left beside a swapped-in database is asking for
trouble.

Check it landed — expect 3,646:

```bash
python scripts/check_chroma_collection.py
```

For the full per-document table, run the corpus cell at the top of
`notebooks/S2_pipeline.ipynb`; it should read `23 of 23 documents in the
collection`.

This gives you byte-identical vectors to everyone else's, which re-embedding
locally would not: the OpenAI API returns slightly different floats per batch,
so two people embedding the same chunk can differ by ~1e-4.

## Rebuilding from scratch instead

You only need this if the corpus changes. It re-embeds all 23 documents via the
OpenAI API — a few cents, and needs `OPEN_AI_API_KEY` in `.env`:

```bash
git clean -xfd vectorstore/
python -m src.ingestion.backfill_vectorstore
```

## Publishing a new snapshot

Keep this to **one person**, so the binary never needs merging:

```bash
tar -czf vectorstore-snapshot.tar.gz -C vectorstore \
    --exclude='*.sqlite3-wal' --exclude='*.sqlite3-shm' .
```

Then commit it. Each snapshot adds ~32MB to history permanently, so only
re-publish when the corpus has actually changed.
