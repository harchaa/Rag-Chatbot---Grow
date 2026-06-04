"""Polite refusal copy + educational/factsheet links for non-factual queries.

PERFORMANCE refusals are distinct from ADVISORY: the problem statement requires
pointing the user to the official factsheet (not a generic AMFI page) for any
returns or performance questions.
"""

from __future__ import annotations

_AMFI_EDU = "https://www.amfiindia.com/investor-corner/knowledge-center"
_SEBI_EDU = "https://www.sebi.gov.in/investor-corner.html"
# HDFC MF factsheets listing page — official source for all performance data
_HDFC_FACTSHEET = "https://www.hdfcfund.com/resources/factsheets"

_REFUSALS = {
    "ADVISORY": {
        "message": (
            "I can only answer factual questions about mutual fund schemes — "
            "such as expense ratios, exit loads, or minimum investment amounts. "
            "For investment guidance, please consult a SEBI-registered financial advisor."
        ),
        "edu_link": _AMFI_EDU,
    },
    "PERFORMANCE": {
        "message": (
            "I don't provide returns, performance data, or NAV history. "
            "For accurate and up-to-date performance information, "
            "please refer to the official HDFC Mutual Fund factsheet."
        ),
        "edu_link": _HDFC_FACTSHEET,
    },
    "OUT_OF_SCOPE": {
        "message": (
            "That question is outside the scope of this assistant. "
            "I can answer factual questions about the HDFC mutual fund schemes "
            "in my knowledge base, such as fees, limits, and scheme details."
        ),
        "edu_link": _AMFI_EDU,
    },
}


def refusal_response(intent: str) -> dict:
    """Return {message, edu_link} for the given intent label."""
    return _REFUSALS.get(intent.upper(), _REFUSALS["OUT_OF_SCOPE"])
