"""Local BGE embedding wrapper (sentence-transformers).

Key BGE requirement: query embeddings need the instruction prefix
"Represent this sentence for searching relevant passages: "
but document embeddings must NOT use it.

The model is loaded lazily on first use so that importing the package
never triggers a slow model download in test/config-only contexts.
"""

from __future__ import annotations

from functools import lru_cache

from mf_assistant.config import settings


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a list of document texts (no query prefix)."""
    if not texts:
        return []
    vecs = _model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vecs.tolist()


def embed_query(text: str) -> list[float]:
    """Embed a single query string (with BGE query instruction prefix)."""
    prefixed = settings.embedding_query_prefix + text
    vec = _model().encode([prefixed], normalize_embeddings=True, show_progress_bar=False)
    return vec[0].tolist()
