"""Output contract enforcement.

Rules (from the problem statement):
- Answer body is ≤ 3 sentences
- No URL in the answer body (LLM must never emit one; we attach it programmatically)
- Citation: exactly one source link, taken from chunk metadata
- Footer: "Last updated from sources: <fetched_at>"
"""

from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _strip_urls(text: str) -> str:
    return _URL_RE.sub("", text).strip()


def _cap_sentences(text: str, max_sentences: int = 3) -> str:
    sentences = _SENTENCE_SPLIT.split(text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    return " ".join(sentences[:max_sentences])


def validate_and_format(
    raw_answer: str,
    citation_url: str,
    fetched_at: str,
) -> dict:
    """Apply all output rules and return {answer, citation_url, fetched_at}.

    The returned `answer` is the clean body text only (≤ 3 sentences, no URLs).
    The caller (UI or pipeline) renders the citation link and footer separately
    so they are always present and always correct.
    """
    clean = _strip_urls(raw_answer)
    clean = _cap_sentences(clean, max_sentences=3)

    return {
        "answer": clean,
        "citation_url": citation_url,
        "fetched_at": fetched_at,
    }
