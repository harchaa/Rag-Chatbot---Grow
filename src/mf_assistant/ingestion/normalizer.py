"""Normalize raw Groww scheme data into a clean, compliant per-scheme document.

COMPLIANCE NOTE — we deliberately EXCLUDE every performance / returns / peer-comparison
field from the corpus (``return_stats``, ``simple_return``, ``sip_return``, ``stats``,
``peerComparison``, ``holdings``, ``analysis``, ``historic_*``). Because those facts never
enter the index, the assistant *cannot* answer performance or comparison questions — it
will fall back to a refusal pointing at the official factsheet. We keep only static,
verifiable scheme attributes (fees, limits, lock-in, benchmark, riskometer, taxation, etc.).

Output shape (one JSON file per scheme in data/processed/):
    {id, source_url, source_type, fetched_at, scheme{...}, facts{...}, sections[{title,text}]}
"""

from __future__ import annotations

import re
from typing import Any


def _clean(text: Any) -> str:
    """Collapse whitespace/newlines and strip; return '' for falsy input."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def _risk(raw: Any) -> str:
    """Normalize the riskometer label (e.g. 'Moderately High Riskometer' -> 'Moderately High')."""
    return re.sub(r"\s*Riskometer$", "", _clean(raw), flags=re.IGNORECASE).strip()


def _rupees(value: Any, decimals: int = 0) -> str | None:
    try:
        return f"₹{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return None


def _lock_in(d: dict | None) -> str:
    d = d or {}
    years, months, days = d.get("years") or 0, d.get("months") or 0, d.get("days") or 0
    if not (years or months or days):
        return "No lock-in period"
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    return " ".join(parts) + " lock-in"


def normalize(raw: dict, source: dict, fetched_at: str) -> dict:
    """Build a clean, compliant scheme document from raw Groww data."""
    fund_house = _clean(raw.get("fund_house")) or _clean(raw.get("amc"))
    name = _clean(raw.get("fund_name")) or source.get("scheme_name", "")
    category = _clean(raw.get("category"))
    sub_category = _clean(raw.get("sub_category"))
    risk = _risk(raw.get("nfo_risk"))
    benchmark = _clean(raw.get("benchmark_name")) or _clean(raw.get("benchmark"))
    fund_manager = _clean(raw.get("fund_manager"))
    expense = raw.get("expense_ratio")
    exit_load = _clean(raw.get("exit_load"))
    lock_in = _lock_in(raw.get("lock_in"))
    stamp = _clean(raw.get("stamp_duty"))
    registrar = _clean(raw.get("registrar_agent"))
    taxation = _clean((raw.get("category_info") or {}).get("tax_impact"))
    description = _clean(raw.get("description"))
    nav, nav_date = raw.get("nav"), _clean(raw.get("nav_date"))
    aum = raw.get("aum")
    min_sip = raw.get("min_sip_investment")
    min_lumpsum = raw.get("min_investment_amount")
    min_add = raw.get("mini_additional_investment")
    min_wd = raw.get("min_withdrawal")

    scheme = {
        "fund_name": name,
        "scheme_name": _clean(raw.get("scheme_name")),
        "amc": fund_house,
        "category": category,
        "sub_category": sub_category,
        "plan_type": _clean(raw.get("plan_type")),
        "scheme_type": _clean(raw.get("scheme_type")),
        "isin": _clean(raw.get("isin")),
        "scheme_code": raw.get("scheme_code"),
        "launch_date": _clean(raw.get("launch_date")),
        "fund_manager": fund_manager,
        "benchmark": benchmark,
        "riskometer": risk,
    }
    facts = {
        "expense_ratio_pct": expense,
        "exit_load": exit_load,
        "lock_in": lock_in,
        "min_sip": min_sip,
        "min_lumpsum": min_lumpsum,
        "min_additional": min_add,
        "min_withdrawal": min_wd,
        "sip_allowed": raw.get("sip_allowed"),
        "lumpsum_allowed": raw.get("lumpsum_allowed"),
        "stamp_duty": stamp,
        "registrar": registrar,
        "aum_crore": aum,
        "nav": nav,
        "nav_date": nav_date,
        "taxation": taxation,
    }

    sections: list[dict[str, str]] = []

    # --- Overview ---
    ov = [f"{name} is a {sub_category} {category} mutual fund offered by {fund_house}.".replace("  ", " ")]
    if risk:
        ov.append(f"Its riskometer classification is {risk}.")
    if benchmark:
        ov.append(f"Its benchmark index is {benchmark}.")
    if fund_manager:
        ov.append(f"The fund manager is {fund_manager}.")
    if scheme["launch_date"]:
        ov.append(f"It was launched on {scheme['launch_date']}.")
    if scheme["isin"]:
        ov.append(f"Its ISIN is {scheme['isin']}.")
    sections.append({"title": "Overview", "text": " ".join(ov)})

    # --- Fees and Charges ---
    fc = []
    if expense is not None:
        fc.append(f"The expense ratio of {name} is {expense}%.")
    if exit_load:
        fc.append(f"The exit load is: {exit_load.rstrip('.')}.")
    if stamp:
        fc.append(f"Stamp duty is {stamp}.")
    if fc:
        sections.append({"title": "Fees and Charges", "text": " ".join(fc)})

    # --- Investment Limits ---
    il = []
    if (m := _rupees(min_sip)) is not None:
        il.append(f"The minimum SIP investment is {m}.")
    if (m := _rupees(min_lumpsum)) is not None:
        il.append(f"The minimum lumpsum (one-time) investment is {m}.")
    if (m := _rupees(min_add)) is not None:
        il.append(f"The minimum additional investment is {m}.")
    if (m := _rupees(min_wd)) is not None:
        il.append(f"The minimum withdrawal amount is {m}.")
    il.append(f"Lock-in: {lock_in}.")
    if raw.get("sip_allowed") is not None:
        il.append(f"SIP investment is {'allowed' if raw.get('sip_allowed') else 'not allowed'}.")
    sections.append({"title": "Investment Limits", "text": " ".join(il)})

    # --- Taxation ---
    if taxation:
        sections.append(
            {"title": "Taxation", "text": f"Taxation for {name} (category: {category}): {taxation}"}
        )

    # --- Fund Size and NAV (current data) ---
    cd = []
    if (a := _rupees(aum, 2)) is not None:
        cd.append(f"The assets under management (AUM) is approximately {a} crore.")
    if nav is not None:
        cd.append(f"The latest NAV is ₹{nav}" + (f" as of {nav_date}." if nav_date else "."))
    if cd:
        sections.append({"title": "Fund Size and NAV", "text": " ".join(cd)})

    # --- Fund House and Registrar ---
    fh = []
    if registrar:
        fh.append(f"The registrar and transfer agent (RTA) for {name} is {registrar}.")
    amc_addr = _clean((raw.get("amc_info") or {}).get("address"))
    if amc_addr:
        fh.append(f"The AMC ({fund_house}) registered address is {amc_addr}.")
    if fh:
        sections.append({"title": "Fund House and Registrar", "text": " ".join(fh)})

    # --- Scheme Description ---
    if description:
        sections.append({"title": "Scheme Description", "text": description})

    return {
        "id": source["id"],
        "source_url": source["url"],
        "source_type": "groww_scheme_page",
        "fetched_at": fetched_at,
        "scheme": scheme,
        "facts": facts,
        "sections": sections,
    }
