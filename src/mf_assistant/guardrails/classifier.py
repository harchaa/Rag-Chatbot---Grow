"""Two-stage intent classifier: rule pre-filter → LLM fallback.

Stage 1 — fast regex rules catch obvious advisory/comparison triggers.
Stage 2 — LLM (8B) resolves ambiguous cases.

Returns: "FACTUAL" | "ADVISORY" | "OUT_OF_SCOPE"
"""

from __future__ import annotations

import re

_ADVISORY_PATTERNS = re.compile(
    r"\b("
    r"should i|should we|is it\b.{0,10}\b(good|worth|safe|right|advisable)|"
    r"recommend|suggest|advice|advise|"
    r"which (is |fund |scheme )?(better|best|good)|"
    r"better than|worse than|vs\.?|versus|compare|"
    r"worth investing|should invest|good investment|"
    r"will (it|this|the fund)|predict|forecast|"
    r"right time|good time|when (should|to) invest"
    r")\b",
    re.IGNORECASE,
)

_OOS_PATTERNS = re.compile(
    r"\b(weather|cricket|football|movie|recipe|news|stock price|crypto|bitcoin)\b",
    re.IGNORECASE,
)


def classify(question: str) -> str:
    """Return FACTUAL, ADVISORY, or OUT_OF_SCOPE."""
    if _OOS_PATTERNS.search(question):
        return "OUT_OF_SCOPE"
    if _ADVISORY_PATTERNS.search(question):
        return "ADVISORY"
    # Ambiguous — ask the LLM classifier
    try:
        from mf_assistant.llm.groq_client import classify_intent
        return classify_intent(question)
    except Exception:
        return "FACTUAL"
