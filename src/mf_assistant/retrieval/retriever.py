"""Dense retrieval: embed the query with BGE and fetch top-k chunks from Chroma."""

from __future__ import annotations

from mf_assistant.config import settings
from mf_assistant.index.embedder import embed_query
from mf_assistant.index.vectorstore import query as chroma_query


def retrieve(
    question: str,
    k: int | None = None,
    scheme_filter: str | None = None,
) -> list[dict]:
    """Return top-k chunks for *question*, optionally filtered by scheme name.

    Each result: {chunk_id, text, metadata, distance}
    Lower distance = more similar (cosine, 0–2 scale).
    """
    embedding = embed_query(question)
    where = {"scheme_name": scheme_filter} if scheme_filter else None
    return chroma_query(embedding, k=k or settings.top_k, where=where)
