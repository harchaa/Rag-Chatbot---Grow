"""PII detection — block PAN, Aadhaar, phone, email, account numbers, OTP context.

On a hit we return a safe message and never log/store the detected value.
"""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),                      # PAN
    re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b"),                  # Aadhaar (12-digit)
    re.compile(r"\b[6-9]\d{9}\b"),                                   # Indian mobile (10-digit)
    re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),  # email
    re.compile(r"\b\d{9,18}\b"),                                     # bank account / folio
    re.compile(r"\botp\b", re.IGNORECASE),                           # OTP context
]


def contains_pii(text: str) -> bool:
    return any(p.search(text) for p in _PATTERNS)


def pii_response() -> str:
    return (
        "For your privacy, please don't share personal details such as PAN, Aadhaar, "
        "account numbers, or OTPs here. I can only answer general factual questions "
        "about mutual fund schemes."
    )
