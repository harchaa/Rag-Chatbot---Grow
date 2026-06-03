"""Phase 2 edge-case tests — see docs/EdgeCases.md (cases P2-1 .. P2-7).

All tests are offline:
- Chunker: exercised on synthetic docs with no I/O.
- Embedder: the prefix logic is tested by monkeypatching the underlying model;
  unicode handling is tested at the chunker level.
- Vectorstore: Chroma is given an in-memory-style temp path so no disk state persists.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import uuid

import pytest

from mf_assistant.ingestion.chunker import _split_text, chunk_document

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------- fixtures / helpers
def make_doc(sections=None, **scheme_overrides) -> dict:
    scheme = {
        "fund_name": "Test Fund",
        "amc": "Test AMC",
        "category": "Equity",
        "sub_category": "Mid Cap",
        "plan_type": "Direct",
        "scheme_type": "Growth",
        "isin": "INF000T01",
        "scheme_code": "1",
        "launch_date": "01-Jan-2020",
        "fund_manager": "Jane",
        "benchmark": "Nifty 50",
        "riskometer": "Moderate",
    }
    scheme.update(scheme_overrides)
    return {
        "id": "test-fund",
        "source_url": "https://groww.in/mutual-funds/test-fund",
        "source_type": "groww_scheme_page",
        "fetched_at": "2026-06-03",
        "scheme": scheme,
        "facts": {},
        "sections": sections
        or [
            {"title": "Overview", "text": "Test Fund is a Mid Cap Equity fund by Test AMC."},
            {"title": "Fees and Charges", "text": "The expense ratio is 0.5%. The exit load is Nil."},
        ],
    }


# ------------------------------------------------------------------ chunker (P2-1..4)
def test_short_section_is_single_chunk():  # P2-1
    doc = make_doc(sections=[{"title": "Overview", "text": "Short text."}])
    chunks = chunk_document(doc, chunk_size=500)
    assert len(chunks) == 1


def test_long_section_splits_with_overlap():  # P2-2
    # Build a text that clearly exceeds chunk_size=10 tokens (~40 chars)
    sentences = ["This is sentence number %02d." % i for i in range(30)]
    long_text = " ".join(sentences)
    parts = _split_text(long_text, chunk_size=10, overlap=3)
    assert len(parts) > 1
    # Every part should be non-empty
    assert all(p.strip() for p in parts)
    # Overlap: later chunk should share content with end of previous chunk
    last_words_of_first = parts[0].split()[-3:]
    assert any(w in parts[1] for w in last_words_of_first)


def test_empty_section_skipped():  # P2-3
    doc = make_doc(
        sections=[
            {"title": "Overview", "text": "Some text."},
            {"title": "Empty", "text": ""},
            {"title": "Whitespace", "text": "   \n  "},
        ]
    )
    chunks = chunk_document(doc)
    titles = [c["metadata"]["section"] for c in chunks]
    assert "Empty" not in titles
    assert "Whitespace" not in titles
    assert "Overview" in titles


def test_chunk_metadata_fields_present():  # P2-4
    doc = make_doc()
    chunks = chunk_document(doc)
    for c in chunks:
        m = c["metadata"]
        assert m["source_url"] == "https://groww.in/mutual-funds/test-fund"
        assert m["fetched_at"] == "2026-06-03"
        assert m["scheme_name"] == "Test Fund"
        assert m["doc_id"] == "test-fund"
        assert "section" in m
        assert "chunk_index" in m


def test_chunk_id_is_deterministic():
    doc = make_doc()
    chunks1 = chunk_document(doc)
    chunks2 = chunk_document(doc)
    assert [c["chunk_id"] for c in chunks1] == [c["chunk_id"] for c in chunks2]


def test_contextual_prefix_in_text():
    doc = make_doc(sections=[{"title": "Fees and Charges", "text": "Expense ratio is 0.5%."}])
    chunk = chunk_document(doc)[0]
    assert "Scheme: Test Fund" in chunk["text"]
    assert "AMC: Test AMC" in chunk["text"]
    assert "Section: Fees and Charges" in chunk["text"]
    assert "Expense ratio is 0.5%." in chunk["text"]


def test_unicode_and_rupee_symbol_handled():  # P2-7 (chunker side)
    doc = make_doc(sections=[{"title": "Limits", "text": "Min SIP is ₹100. Exit load: Nil. AUM: ₹50,000 crore."}])
    chunks = chunk_document(doc)
    assert len(chunks) == 1
    assert "₹100" in chunks[0]["text"]


# ------------------------------------------------------------------ embedder (P2-6)
def test_embed_query_uses_prefix(monkeypatch):  # P2-6
    captured = {}

    def fake_encode(texts, **_kw):
        captured["texts"] = texts
        import numpy as np
        return np.zeros((len(texts), 4), dtype="float32")

    import mf_assistant.index.embedder as emb_mod
    from mf_assistant.config import settings

    # staticmethod prevents Python from injecting `self` when called on an instance
    monkeypatch.setattr(emb_mod, "_model", lambda: type("M", (), {"encode": staticmethod(fake_encode)})())
    emb_mod.embed_query("what is expense ratio")
    assert captured["texts"][0].startswith(settings.embedding_query_prefix)


def test_embed_documents_no_prefix(monkeypatch):  # P2-6
    captured = {}

    def fake_encode(texts, **_kw):
        captured["texts"] = texts
        import numpy as np
        return np.zeros((len(texts), 4), dtype="float32")

    import mf_assistant.index.embedder as emb_mod
    from mf_assistant.config import settings

    monkeypatch.setattr(emb_mod, "_model", lambda: type("M", (), {"encode": staticmethod(fake_encode)})())
    emb_mod.embed_documents(["some document text"])
    assert not captured["texts"][0].startswith(settings.embedding_query_prefix)


def test_embed_documents_empty_list(monkeypatch):
    import mf_assistant.index.embedder as emb_mod
    monkeypatch.setattr(emb_mod, "_model", lambda: None)
    assert emb_mod.embed_documents([]) == []


# ---------------------------------------------------------------- vectorstore (P2-5)
def test_upsert_idempotent(monkeypatch, tmp_path):  # P2-5
    """Upserting the same chunks twice must not double the count."""
    import mf_assistant.index.vectorstore as vs

    monkeypatch.setattr(vs.cfg, "chroma_dir", tmp_path / ".chroma")
    monkeypatch.setattr(vs.cfg, "collection_name", f"test_{uuid.uuid4().hex[:8]}")
    vs._client.cache_clear()

    chunks = chunk_document(make_doc())
    dummy_emb = [[0.1] * 384] * len(chunks)
    for c, e in zip(chunks, dummy_emb):
        c["embedding"] = e

    col = vs._collection()
    col.upsert(
        ids=[c["chunk_id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        embeddings=[c["embedding"] for c in chunks],
        metadatas=[vs._clean_meta(c["metadata"]) for c in chunks],
    )
    count_after_first = col.count()
    col.upsert(
        ids=[c["chunk_id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        embeddings=[c["embedding"] for c in chunks],
        metadatas=[vs._clean_meta(c["metadata"]) for c in chunks],
    )
    assert col.count() == count_after_first  # no duplicates


def test_metadata_none_values_cleaned(monkeypatch, tmp_path):
    import mf_assistant.index.vectorstore as vs

    monkeypatch.setattr(vs.cfg, "chroma_dir", tmp_path / ".chroma")
    monkeypatch.setattr(vs.cfg, "collection_name", f"test_{uuid.uuid4().hex[:8]}")
    vs._client.cache_clear()

    doc = make_doc(sections=[{"title": "Overview", "text": "Test."}])
    doc["scheme"]["amc"] = None  # inject a None value
    chunks = chunk_document(doc)
    # _clean_meta must convert None -> "" without raising
    for c in chunks:
        cleaned = vs._clean_meta(c["metadata"])
        assert None not in cleaned.values()
