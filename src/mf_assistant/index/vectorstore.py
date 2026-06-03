"""Persistent ChromaDB vector store for scheme chunks.

Chroma upserts are idempotent by chunk_id, so re-running build_index.py
never creates duplicates — it updates any changed chunks in place.

Metadata values must be str/int/float/bool; None is not allowed by Chroma.
_clean_meta() converts None → "" so callers don't need to worry about it.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from mf_assistant.config import settings as cfg


def _clean_meta(meta: dict[str, Any]) -> dict[str, Any]:
    return {k: ("" if v is None else v) for k, v in meta.items()}


@lru_cache(maxsize=1)
def _client() -> chromadb.PersistentClient:
    cfg.chroma_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(cfg.chroma_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def _collection():
    return _client().get_or_create_collection(
        name=cfg.collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(chunks: list[dict]) -> None:
    """Upsert a list of chunk dicts (from chunker.chunk_document) into Chroma."""
    if not chunks:
        return
    col = _collection()
    col.upsert(
        ids=[c["chunk_id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[_clean_meta(c["metadata"]) for c in chunks],
    )


def query(
    embedding: list[float],
    k: int | None = None,
    where: dict | None = None,
) -> list[dict]:
    """Return up to k results for a query embedding.

    Each result dict: {chunk_id, text, metadata, distance}
    Distance is cosine (0 = identical, 2 = opposite). Lower = more similar.
    """
    n = k or cfg.top_k
    col = _collection()
    kwargs: dict[str, Any] = dict(
        query_embeddings=[embedding],
        n_results=min(n, col.count() or 1),
        include=["documents", "metadatas", "distances"],
    )
    if where:
        kwargs["where"] = where

    res = col.query(**kwargs)
    results = []
    for cid, doc, meta, dist in zip(
        res["ids"][0],
        res["documents"][0],
        res["metadatas"][0],
        res["distances"][0],
    ):
        results.append({"chunk_id": cid, "text": doc, "metadata": meta, "distance": dist})
    return results


def count() -> int:
    return _collection().count()


def reset_collection() -> None:
    """Drop and recreate the collection. Used in tests / full rebuilds."""
    try:
        _client().delete_collection(cfg.collection_name)
    except Exception:
        pass  # doesn't exist yet — that's fine
    _client.cache_clear()
    _collection()  # recreate immediately so the collection exists for upserts
