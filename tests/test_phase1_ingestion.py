"""Phase 1 edge-case tests — see docs/EdgeCases.md (cases P1-1 .. P1-21).

All tests are offline: the scraper is exercised on synthetic HTML / mocked requests,
and the normalizer on synthetic raw dicts. No network access.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from mf_assistant.ingestion import scraper
from mf_assistant.ingestion.normalizer import normalize

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = {
    "id": "test-fund",
    "url": "https://groww.in/mutual-funds/test-fund-direct-growth",
    "scheme_name": "Sources.yaml Label (should be overridden)",
}


# --------------------------------------------------------------------------- helpers
def make_raw(**overrides) -> dict:
    """A realistic mfServerSideData dict, including performance fields that MUST be dropped."""
    raw = {
        "fund_name": "Test Equity Fund",
        "scheme_name": "Test Equity Fund Direct Growth",
        "fund_house": "Test AMC Mutual Fund",
        "amc": "TEST",
        "category": "Equity",
        "sub_category": "Mid Cap",
        "plan_type": "Direct",
        "scheme_type": "Growth",
        "isin": "INF000TEST01",
        "scheme_code": "999999",
        "launch_date": "01-Jan-2013",
        "fund_manager": "Jane Doe",
        "benchmark": "NIFTY Midcap 150 TRI",
        "benchmark_name": "NIFTY Midcap 150 Total Return Index",
        "nfo_risk": "Moderately High Riskometer",
        "expense_ratio": "0.73",
        "exit_load": "Exit load of 1% if redeemed within 1 year.\n",
        "lock_in": {"years": None, "months": None, "days": None},
        "min_sip_investment": 100,
        "min_investment_amount": 5000,
        "mini_additional_investment": 1000,
        "min_withdrawal": 500,
        "sip_allowed": True,
        "lumpsum_allowed": True,
        "stamp_duty": "0.005% (from July 1st, 2020)",
        "registrar_agent": "CAMS",
        "aum": 12345.678,
        "nav": 221.322,
        "nav_date": "29-May-2026",
        "category_info": {"tax_impact": "If you redeem within one year, returns are taxed at 20%."},
        "amc_info": {"address": "Some  Address,\n Mumbai 400020"},
        "description": "The scheme seeks\n   long-term capital appreciation.",
        # --- performance data that must NEVER leak into the corpus (C-1) ---
        "return_stats": [{"return1y": "PERF_SENTINEL_1Y"}],
        "simple_return": {"return1y": "PERF_SENTINEL_SIMPLE"},
        "sip_return": {"return3y": "PERF_SENTINEL_SIP"},
        "peerComparison": [{"name": "PEER_SENTINEL"}],
        "holdings": [{"company_name": "HOLDING_SENTINEL"}],
        "stats": [{"title": "STATS_SENTINEL"}],
        "analysis": [{"analysis_desc": "ANALYSIS_SENTINEL"}],
        "historic_fund_expense": [{"expense_ratio": "HIST_SENTINEL"}],
    }
    raw.update(overrides)
    return raw


def doc(**overrides) -> dict:
    return normalize(make_raw(**overrides), SOURCE, fetched_at="2026-05-31")


def sections_by_title(d: dict) -> dict[str, str]:
    return {s["title"]: s["text"] for s in d["sections"]}


def html_with(next_data: str) -> str:
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        f"{next_data}</script></body></html>"
    )


def valid_next_data(fund_name: str = "X") -> str:
    return json.dumps({"props": {"pageProps": {"mfServerSideData": {"fund_name": fund_name}}}})


def load_refresh_module():
    path = REPO_ROOT / "scripts" / "refresh_data.py"
    spec = importlib.util.spec_from_file_location("refresh_data", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------- scraper (P1-1..7)
def test_extract_valid():  # P1-7
    out = scraper._extract(html_with(valid_next_data("HDFC Test")), "u")
    assert out["fund_name"] == "HDFC Test"


def test_extract_missing_next_data():  # P1-1
    with pytest.raises(scraper.ScrapeError):
        scraper._extract("<html><body>no blob here</body></html>", "u")


def test_extract_malformed_json():  # P1-2
    with pytest.raises(scraper.ScrapeError):
        scraper._extract(html_with("{ not valid json "), "u")


def test_extract_missing_mfserversidedata():  # P1-3
    nd = json.dumps({"props": {"pageProps": {}}})
    with pytest.raises(scraper.ScrapeError):
        scraper._extract(html_with(nd), "u")


def test_extract_missing_fund_name():  # P1-4
    nd = json.dumps({"props": {"pageProps": {"mfServerSideData": {"category": "Equity"}}}})
    with pytest.raises(scraper.ScrapeError):
        scraper._extract(html_with(nd), "u")


def test_fetch_retries_and_raises(monkeypatch):  # P1-5
    calls = {"n": 0}

    def boom(*_a, **_k):
        calls["n"] += 1
        raise scraper.requests.RequestException("network down")

    monkeypatch.setattr(scraper.requests, "get", boom)
    monkeypatch.setattr(scraper.time, "sleep", lambda *_a, **_k: None)
    with pytest.raises(scraper.ScrapeError):
        scraper.fetch_scheme_data("u", retries=3)
    assert calls["n"] == 3


def test_fetch_success(monkeypatch):  # P1-6
    class FakeResp:
        text = html_with(valid_next_data("Fetched Fund"))

        def raise_for_status(self):
            return None

    monkeypatch.setattr(scraper.requests, "get", lambda *_a, **_k: FakeResp())
    assert scraper.fetch_scheme_data("u")["fund_name"] == "Fetched Fund"


# --------------------------------------------------------------- normalizer (P1-8..19)
def test_excludes_performance_fields():  # P1-8 (C-1)
    blob = json.dumps(doc(), ensure_ascii=False)
    for sentinel in (
        "PERF_SENTINEL_1Y", "PERF_SENTINEL_SIMPLE", "PERF_SENTINEL_SIP",
        "PEER_SENTINEL", "HOLDING_SENTINEL", "STATS_SENTINEL",
        "ANALYSIS_SENTINEL", "HIST_SENTINEL",
        "return1y", "peerComparison", "simple_return", "return_stats", "holdings",
    ):
        assert sentinel not in blob, f"performance data leaked into corpus: {sentinel}"


def test_lock_in_absent():  # P1-9
    assert doc()["facts"]["lock_in"] == "No lock-in period"


def test_lock_in_elss():  # P1-10
    d = doc(lock_in={"years": 3, "months": 0, "days": 0})
    assert d["facts"]["lock_in"] == "3 years lock-in"


def test_riskometer_suffix_stripped():  # P1-11
    assert doc()["scheme"]["riskometer"] == "Moderately High"


def test_exit_load_nil():  # P1-12
    d = doc(exit_load="Nil")
    assert d["facts"]["exit_load"] == "Nil"
    assert "The exit load is: Nil." in sections_by_title(d)["Fees and Charges"]


def test_exit_load_whitespace():  # P1-13
    el = doc()["facts"]["exit_load"]
    assert el == "Exit load of 1% if redeemed within 1 year."
    assert "\n" not in el and not el.endswith(" ")


def test_missing_taxation_omitted():  # P1-14
    assert "Taxation" not in sections_by_title(doc(category_info=None))


def test_missing_aum_nav_omitted():  # P1-15
    assert "Fund Size and NAV" not in sections_by_title(doc(aum=None, nav=None))


def test_whitespace_collapsed():  # P1-16
    desc = sections_by_title(doc())["Scheme Description"]
    assert desc == "The scheme seeks long-term capital appreciation."


def test_fund_name_authoritative():  # P1-17
    # sources.yaml label is intentionally different; the page name must win.
    assert doc()["scheme"]["fund_name"] == "Test Equity Fund"


def test_rupees_formatting():  # P1-18
    limits = sections_by_title(doc())["Investment Limits"]
    assert "₹100" in limits          # min SIP
    assert "₹5,000" in limits        # min lumpsum, with thousands separator


def test_required_fields():  # P1-19
    d = doc()
    assert set(d) >= {"id", "source_url", "source_type", "fetched_at", "scheme", "facts", "sections"}
    assert d["source_url"] == SOURCE["url"]
    assert d["fetched_at"] == "2026-05-31"
    assert len(d["sections"]) >= 1


# ------------------------------------------------------------- orchestration (P1-20..21)
def test_refresh_filter_unknown_id(monkeypatch):  # P1-20
    refresh = load_refresh_module()

    def fail_if_called(*_a, **_k):  # network must NOT be touched
        raise AssertionError("fetch_scheme_data should not be called for an unknown id")

    monkeypatch.setattr(refresh, "fetch_scheme_data", fail_if_called)
    assert refresh.main(["does-not-exist"]) == 1


def test_partial_failure_resilient(monkeypatch, tmp_path):  # P1-21
    refresh = load_refresh_module()
    bad_id = "hdfc-equity"

    def fake_fetch(url, **_k):
        if bad_id in url:
            raise refresh.ScrapeError("simulated 404")
        return make_raw()

    monkeypatch.setattr(refresh, "fetch_scheme_data", fake_fetch)
    monkeypatch.setattr(refresh.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(refresh.settings, "raw_dir", tmp_path / "raw")
    monkeypatch.setattr(refresh.settings, "processed_dir", tmp_path / "processed")

    rc = refresh.main([])  # process all sources from sources.yaml
    assert rc == 2  # non-zero because one failed
    produced = {p.stem for p in (tmp_path / "processed").glob("*.json")}
    assert bad_id not in produced            # failed source produced no file
    assert "hdfc-mid-cap" in produced        # others still processed
