"""Central configuration. Values can be overridden via environment variables or .env.

All defaults are chosen for the design in docs/Architecture.md. Nothing here triggers
heavy imports (no torch/chromadb), so importing the package stays fast.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root:  src/mf_assistant/config.py -> parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Groq (LLM) ---
    groq_api_key: str = ""
    groq_generation_model: str = "llama-3.3-70b-versatile"
    groq_classifier_model: str = "llama-3.1-8b-instant"
    llm_temperature: float = 0.1
    llm_timeout_seconds: int = 30

    # --- Embeddings / reranker (local, via sentence-transformers) ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_query_prefix: str = "Represent this sentence for searching relevant passages: "
    reranker_model: str = "BAAI/bge-reranker-base"
    use_reranker: bool = True

    # --- Retrieval ---
    top_k: int = 6              # dense candidates
    rerank_top_n: int = 3       # kept after reranking
    score_threshold: float = 0.30  # answerability gate (below -> "not in sources")

    # --- Chunking ---
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 80

    # --- Paths ---
    data_dir: Path = PROJECT_ROOT / "data"
    raw_dir: Path = PROJECT_ROOT / "data" / "raw"
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    sources_file: Path = PROJECT_ROOT / "data" / "sources.yaml"
    chroma_dir: Path = PROJECT_ROOT / ".chroma"
    collection_name: str = "mf_facts"


settings = Settings()
