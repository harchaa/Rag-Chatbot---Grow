"""Split processed scheme documents into retrievable chunks.

Design (see Architecture.md §5):
- One chunk per section for most sections (they are all < 100 tokens in our corpus).
  The recursive splitter handles any future sections that exceed chunk_size.
- Every chunk gets a contextual prefix  "Scheme: X | AMC: Y | Section: Z"
  prepended to the text. This is the "contextual retrieval lite" trick: short
  factual chunks retrieve far better when they carry scheme context.
- Rich metadata (source_url + fetched_at) drives citations and the footer date.
"""

from __future__ import annotations

import re
import unicodedata


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _section_slug(title: str) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into token-budget chunks; preserve sentence boundaries where possible."""
    if _approx_tokens(text) <= chunk_size:
        return [text.strip()]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) <= 1:
        # No sentence boundaries — hard character split with overlap
        step = chunk_size * 4
        ov = overlap * 4
        return [text[i : i + step].strip() for i in range(0, len(text), step - ov) if text[i : i + step].strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sent in sentences:
        sent_tokens = _approx_tokens(sent)
        if current_tokens + sent_tokens > chunk_size and current:
            chunks.append(" ".join(current))
            # carry overlap sentences into next chunk
            tail: list[str] = []
            tail_tokens = 0
            for s in reversed(current):
                t = _approx_tokens(s)
                if tail_tokens + t <= overlap:
                    tail.insert(0, s)
                    tail_tokens += t
                else:
                    break
            current, current_tokens = tail, tail_tokens
        current.append(sent)
        current_tokens += sent_tokens

    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if c.strip()] or [text.strip()]


def chunk_document(doc: dict, chunk_size: int = 500, overlap: int = 80) -> list[dict]:
    """Return a list of chunk dicts for a single processed scheme document.

    Each dict:
        chunk_id  str   — stable, deterministic ID used as the Chroma document key
        text      str   — contextually-prefixed text (what gets embedded and retrieved)
        metadata  dict  — fields Chroma stores alongside the embedding
    """
    scheme = doc["scheme"]
    scheme_name = scheme.get("fund_name") or doc["id"]
    amc = scheme.get("amc", "")
    source_url = doc["source_url"]
    source_type = doc["source_type"]
    fetched_at = doc["fetched_at"]
    doc_id = doc["id"]

    chunks: list[dict] = []
    for section in doc.get("sections", []):
        title = section.get("title", "")
        raw_text = (section.get("text") or "").strip()
        if not raw_text:
            continue

        prefix = f"Scheme: {scheme_name} | AMC: {amc} | Section: {title}"
        slug = _section_slug(title)
        splits = _split_text(raw_text, chunk_size, overlap)

        for i, part in enumerate(splits):
            chunk_id = f"{doc_id}__{slug}__{i}"
            text = f"{prefix}\n{part}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": text,
                    "metadata": {
                        "doc_id": doc_id,
                        "scheme_name": scheme_name,
                        "amc": amc,
                        "category": scheme.get("category", ""),
                        "section": title,
                        "source_url": source_url,
                        "source_type": source_type,
                        "fetched_at": fetched_at,
                        "chunk_index": i,
                    },
                }
            )

    return chunks
