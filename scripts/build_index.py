"""Phase 2 — Build the Chroma vector index from data/processed/ documents.

Usage:
    python scripts/build_index.py           # index all processed docs
    python scripts/build_index.py --reset   # wipe + rebuild from scratch

The index is idempotent: re-running without --reset upserts changed chunks in
place (because chunk IDs are deterministic). Use --reset only for a full rebuild
(e.g. after changing chunk_size or the embedding model).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mf_assistant.config import settings
from mf_assistant.index import vectorstore
from mf_assistant.ingestion.chunker import chunk_document


def load_docs() -> list[dict]:
    paths = sorted(settings.processed_dir.glob("*.json"))
    if not paths:
        print(f"No processed docs found in {settings.processed_dir}")
        sys.exit(1)
    return [json.loads(p.read_text(encoding="utf-8")) for p in paths]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Wipe the collection before building.")
    args = parser.parse_args(argv)

    if args.reset:
        print("Resetting collection...")
        vectorstore.reset_collection()

    docs = load_docs()
    print(f"Loaded {len(docs)} processed documents  (chunk_size={settings.chunk_size_tokens} tok)")

    all_chunks: list[dict] = []
    for doc in docs:
        chunks = chunk_document(doc, settings.chunk_size_tokens, settings.chunk_overlap_tokens)
        print(f"  {doc['id']:35} {len(chunks):2} chunks")
        all_chunks.extend(chunks)

    if not all_chunks:
        print("No chunks produced — nothing to index.")
        return 1

    print(f"\nEmbedding {len(all_chunks)} chunks (model: {settings.embedding_model}) ...")
    # Import here so tests can mock embedder without loading the model
    from mf_assistant.index.embedder import embed_documents

    texts = [c["text"] for c in all_chunks]
    embeddings = embed_documents(texts)

    print("Upserting into Chroma ...")
    for chunk, emb in zip(all_chunks, embeddings):
        chunk["embedding"] = emb

    # Chroma upsert accepts embeddings separately
    import chromadb  # noqa: F401 — confirm available

    col_chunks_with_emb = all_chunks
    from mf_assistant.config import settings as cfg
    from mf_assistant.index.vectorstore import _clean_meta, _collection

    col = _collection()
    col.upsert(
        ids=[c["chunk_id"] for c in col_chunks_with_emb],
        documents=[c["text"] for c in col_chunks_with_emb],
        embeddings=[c["embedding"] for c in col_chunks_with_emb],
        metadatas=[_clean_meta(c["metadata"]) for c in col_chunks_with_emb],
    )

    total = vectorstore.count()
    print(f"\nDone. Collection '{cfg.collection_name}' now has {total} chunks  -> {cfg.chroma_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
