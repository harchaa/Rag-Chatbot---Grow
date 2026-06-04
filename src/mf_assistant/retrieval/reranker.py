"""Cross-encoder reranking with BAAI/bge-reranker-base.

Why rerank here specifically:
Every factual answer must cite EXACTLY ONE source. The reranker picks the single
most relevant chunk from the dense top-k candidates, which directly maps to the
single-citation requirement. Without reranking we'd have to pick arbitrarily.

The model is loaded lazily (same pattern as the embedder) so importing this module
in test/config contexts never triggers a download.
"""

from __future__ import annotations

from functools import lru_cache

from mf_assistant.config import settings


@lru_cache(maxsize=1)
def _cross_encoder():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(settings.reranker_model)


def rerank(question: str, candidates: list[dict], top_n: int | None = None) -> list[dict]:
    """Score candidates with the cross-encoder and return them sorted best-first.

    Each candidate dict must have a "text" key (the chunk text).
    Returns the same dicts with an added "rerank_score" key.
    """
    if not candidates:
        return []

    n = top_n or settings.rerank_top_n
    pairs = [(question, c["text"]) for c in candidates]
    scores = _cross_encoder().predict(pairs)

    ranked = sorted(
        [dict(c, rerank_score=float(s)) for c, s in zip(candidates, scores)],
        key=lambda x: x["rerank_score"],
        reverse=True,
    )
    return ranked[:n]
