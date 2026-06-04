"""Phase 3 edge-case tests — see docs/EdgeCases.md (cases P3-1 .. P3-7).

All Groq calls are mocked so tests run offline. The retriever and reranker are also
mocked so we can test the pipeline logic in isolation.
"""

from __future__ import annotations

import re

import pytest

from mf_assistant.guardrails.validators import validate_and_format, _cap_sentences, _strip_urls
from mf_assistant.guardrails.classifier import classify
from mf_assistant.guardrails.pii import contains_pii, pii_response
from mf_assistant.guardrails.refusals import refusal_response


# ------------------------------------------------------------------- validators (P3-4,5)
def test_answer_capped_at_3_sentences():  # P3-4 (C-2)
    long = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
    out = validate_and_format(long, "https://example.com", "2026-06-04")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", out["answer"].strip()) if s]
    assert len(sentences) <= 3


def test_url_stripped_from_answer_body():  # P3-5 (C-3)
    raw = "The expense ratio is 0.73%. See https://groww.in/mutual-funds/hdfc-mid-cap for details."
    out = validate_and_format(raw, "https://groww.in/mutual-funds/hdfc-mid-cap", "2026-06-04")
    assert "https://" not in out["answer"]
    assert "groww.in" not in out["answer"]


def test_citation_attached_from_metadata():  # P3-5 (C-3)
    out = validate_and_format("The ratio is 0.73%.", "https://groww.in/mutual-funds/hdfc-mid-cap", "2026-06-04")
    assert out["citation_url"] == "https://groww.in/mutual-funds/hdfc-mid-cap"
    assert out["fetched_at"] == "2026-06-04"


def test_footer_date_present():  # (C-4)
    out = validate_and_format("Some answer.", "https://x.com", "2026-06-04")
    assert out["fetched_at"] == "2026-06-04"


def test_empty_answer_handled():
    out = validate_and_format("", "https://x.com", "2026-06-04")
    assert out["answer"] == ""


# ------------------------------------------------------------------- classifier (P3-3)
@pytest.mark.parametrize("q,expected", [
    ("Should I invest in HDFC Mid Cap?", "ADVISORY"),
    ("Which is better, HDFC Mid Cap or HDFC Small Cap?", "ADVISORY"),
    ("Is it a good fund?", "ADVISORY"),
    ("What is the weather today?", "OUT_OF_SCOPE"),
    ("cricket score today?", "OUT_OF_SCOPE"),
])
def test_rule_classifier_catches_advisory_and_oos(q, expected):
    # Rules-only test — does not call Groq
    from mf_assistant.guardrails import classifier as clf_mod
    import mf_assistant.guardrails.classifier as clf_mod2
    result = clf_mod._ADVISORY_PATTERNS.search(q) or clf_mod._OOS_PATTERNS.search(q)
    if expected in ("ADVISORY",):
        assert clf_mod._ADVISORY_PATTERNS.search(q), f"Advisory pattern should match: {q}"
    else:
        assert clf_mod._OOS_PATTERNS.search(q), f"OOS pattern should match: {q}"


# ------------------------------------------------------------------- PII guard (C-5)
@pytest.mark.parametrize("text", [
    "My PAN is ABCDE1234F",
    "Aadhaar 9999 8888 7777",
    "call me at 9876543210",
    "email me at user@example.com",
    "my account number is 123456789012",
    "share my OTP here",
])
def test_pii_detected(text):
    assert contains_pii(text), f"PII not detected in: {text}"


def test_pii_response_is_safe():
    resp = pii_response()
    assert "PAN" in resp or "personal" in resp.lower()
    # Must not contain any instruction to do something risky
    assert "invest" not in resp.lower()


def test_non_pii_not_flagged():
    safe = "What is the expense ratio of HDFC Mid Cap Fund?"
    assert not contains_pii(safe)


# ------------------------------------------------------------------- refusals (C-6)
def test_advisory_refusal_has_edu_link():
    resp = refusal_response("ADVISORY")
    assert resp["edu_link"].startswith("https://")
    assert "investment" in resp["message"].lower() or "advisor" in resp["message"].lower()


def test_oos_refusal_message():
    resp = refusal_response("OUT_OF_SCOPE")
    assert resp["edu_link"].startswith("https://")
    assert len(resp["message"]) > 10


# ------------------------------------------------------------------- pipeline (P3-1,2,6,7)
def _make_chunk(scheme="HDFC Mid Cap Fund", section="Fees and Charges",
                url="https://groww.in/mutual-funds/hdfc-mid-cap", date="2026-06-04"):
    return {
        "chunk_id": "hdfc-mid-cap__fees_and_charges__0",
        "text": f"Scheme: {scheme} | AMC: HDFC Mutual Fund | Section: {section}\nThe expense ratio is 0.73%.",
        "metadata": {"scheme_name": scheme, "section": section,
                     "source_url": url, "fetched_at": date},
        "distance": 0.12,
        "rerank_score": 2.5,
    }


def test_factual_happy_path(monkeypatch):  # P3-1
    import mf_assistant.pipeline.rag as rag

    monkeypatch.setattr(rag, "retrieve", lambda q, **_: [_make_chunk()])
    monkeypatch.setattr(rag, "rerank", lambda q, c, **_: [dict(c[0], rerank_score=2.5)])
    monkeypatch.setattr(rag, "generate", lambda ctx, q: "The expense ratio of HDFC Mid Cap Fund is 0.73%.")

    r = rag.ask("What is the expense ratio of HDFC Mid Cap Fund?")
    assert not r.was_refused
    assert "0.73" in r.answer
    assert r.citation_url == "https://groww.in/mutual-funds/hdfc-mid-cap"
    assert r.fetched_at == "2026-06-04"


def test_not_in_sources_low_score(monkeypatch):  # P3-2
    import mf_assistant.pipeline.rag as rag
    from mf_assistant.config import settings

    low_score_chunk = dict(_make_chunk(), rerank_score=-5.0)  # well below threshold
    monkeypatch.setattr(rag, "retrieve", lambda q, **_: [low_score_chunk])
    monkeypatch.setattr(rag, "rerank", lambda q, c, **_: [low_score_chunk])

    r = rag.ask("What is the fund manager's salary?")
    assert r.was_refused
    assert r.refusal_reason == "not_in_sources"


def test_advisory_query_refused(monkeypatch):  # P3 advisory path
    import mf_assistant.pipeline.rag as rag
    # Ensure retrieve is never called for an advisory query
    monkeypatch.setattr(rag, "retrieve", lambda *a, **k: (_ for _ in ()).throw(AssertionError("retrieve should not be called")))

    r = rag.ask("Should I invest in HDFC Mid Cap Fund?")
    assert r.was_refused
    assert r.refusal_reason == "advisory"


def test_empty_query_handled(monkeypatch):  # P3-7
    import mf_assistant.pipeline.rag as rag
    # Empty string should either return not_in_sources or be refused — must not crash
    monkeypatch.setattr(rag, "retrieve", lambda q, **_: [])
    r = rag.ask("   ")
    assert r.was_refused  # empty → no candidates → not_in_sources


def test_groq_error_handled(monkeypatch):  # P3-6
    import mf_assistant.pipeline.rag as rag

    monkeypatch.setattr(rag, "retrieve", lambda q, **_: [_make_chunk()])
    monkeypatch.setattr(rag, "rerank", lambda q, c, **_: [dict(c[0], rerank_score=2.5)])
    monkeypatch.setattr(rag, "generate", lambda ctx, q: (_ for _ in ()).throw(Exception("Groq timeout")))

    with pytest.raises(Exception, match="Groq timeout"):
        # Pipeline propagates the error — UI layer handles display
        rag.ask("What is the expense ratio?")
