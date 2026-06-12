"""Polite refusal copy for non-factual queries.

All links stay within Groww — no external AMFI/SEBI/AMC URLs.
"""

from __future__ import annotations

# All refusal links point to Groww's HDFC MF section — consistent with the corpus
_GROWW_HDFC = "https://groww.in/mutual-funds/amc/hdfc-mutual-funds"

_REFUSALS = {
    "ADVISORY": {
        "message": (
            "I can only answer factual questions about mutual fund schemes — "
            "such as expense ratios, exit loads, or minimum investment amounts. "
            "For investment guidance, please consult a qualified financial advisor."
        ),
        "edu_link": _GROWW_HDFC,
    },
    "PERFORMANCE": {
        "message": (
            "I don't provide returns, performance data, or NAV history. "
            "For up-to-date performance information, please visit the scheme page directly."
        ),
        "edu_link": _GROWW_HDFC,
    },
    "OUT_OF_SCOPE": {
        "message": (
            "That question is outside the scope of this assistant. "
            "I can answer factual questions about the HDFC mutual fund schemes "
            "in my knowledge base, such as fees, limits, and scheme details."
        ),
        "edu_link": _GROWW_HDFC,
    },
}


def refusal_response(intent: str) -> dict:
    """Return {message, edu_link} for the given intent label."""
    return _REFUSALS.get(intent.upper(), _REFUSALS["OUT_OF_SCOPE"])
