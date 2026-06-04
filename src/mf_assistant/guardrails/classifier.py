"""Two-stage intent classifier: rule pre-filter → LLM fallback.

Stage 1 — fast regex rules catch obvious advisory/comparison/performance triggers.
Stage 2 — LLM (8B) resolves ambiguous cases.

Returns: "FACTUAL" | "ADVISORY" | "PERFORMANCE" | "OUT_OF_SCOPE"

PERFORMANCE is a distinct label (not ADVISORY) because the problem statement requires
a specific response: point the user to the official factsheet rather than a generic
refusal. Neither returns data nor peer-comparisons are in the corpus (compliance C-1).
"""

from __future__ import annotations

import re

_ADVISORY_PATTERNS = re.compile(
    r"\b("
    r"should i|should we|"
    r"is it\b.{0,10}\b(good|worth|safe|right|advisable)|"
    r"good for (me|us|my|our)|"
    r"recommend|suggest|advice|advise|"
    r"which\b.{0,20}\b(better|best|good)\b|"
    r"\bthe best (fund|scheme|option|choice)\b|"
    r"better than|worse than|vs\.?|versus|compare|"
    r"worth investing|should invest|good investment|"
    r"will (it|this|the fund)|predict|forecast|"
    r"right time|good time|when (should|to) invest"
    r")\b",
    re.IGNORECASE,
)

# Performance / returns queries — prohibited by the problem statement.
# Response must point to the official factsheet, not answer or give a generic refusal.
_PERFORMANCE_PATTERNS = re.compile(
    r"\b("
    r"return(s)?|performance|performed|performing|"
    r"cagr|xirr|annualised|annualized|"
    r"gain(s|ed)?|profit|loss(es)?|"
    r"nav history|historical nav|past nav|"
    r"how much.{0,20}(grew|grow|earned|made)|"
    r"1\s*yr?|3\s*yr?|5\s*yr?|10\s*yr?|"
    r"last year|this year|over.{0,10}year"
    r")\b",
    re.IGNORECASE,
)

_OOS_PATTERNS = re.compile(
    r"\b(weather|cricket|football|movie|recipe|news|stock price|crypto|bitcoin)\b",
    re.IGNORECASE,
)


def classify(question: str) -> str:
    """Return FACTUAL, ADVISORY, PERFORMANCE, or OUT_OF_SCOPE."""
    if _OOS_PATTERNS.search(question):
        return "OUT_OF_SCOPE"
    if _ADVISORY_PATTERNS.search(question):
        return "ADVISORY"
    if _PERFORMANCE_PATTERNS.search(question):
        return "PERFORMANCE"
    # Ambiguous — ask the LLM classifier
    try:
        from mf_assistant.llm.groq_client import classify_intent
        return classify_intent(question)
    except Exception:
        return "FACTUAL"
