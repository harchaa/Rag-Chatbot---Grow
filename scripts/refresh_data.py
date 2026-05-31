"""Phase 1 ingestion — scrape every source in sources.yaml into raw + processed JSON.

Usage:
    python scripts/refresh_data.py                       # all sources
    python scripts/refresh_data.py hdfc-mid-cap hdfc-equity   # only these ids

Raw snapshots (verbatim Groww data) go to data/raw/ (git-ignored, local cache).
Clean compliant docs go to data/processed/ (versioned — this is the audit trail).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date

import yaml

from mf_assistant.config import settings
from mf_assistant.ingestion.normalizer import normalize
from mf_assistant.ingestion.scraper import ScrapeError, fetch_scheme_data


def load_sources() -> list[dict]:
    with open(settings.sources_file, encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def _write_json(path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str]) -> int:
    only = set(argv)
    sources = load_sources()
    if only:
        sources = [s for s in sources if s["id"] in only]
        if not sources:
            print(f"No sources match {sorted(only)}")
            return 1

    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = date.today().isoformat()

    ok = fail = 0
    for i, src in enumerate(sources):
        sid = src["id"]
        try:
            raw = fetch_scheme_data(src["url"])
            _write_json(settings.raw_dir / f"{sid}.json", raw)
            doc = normalize(raw, src, fetched_at)
            _write_json(settings.processed_dir / f"{sid}.json", doc)
            print(f"[ok]   {sid:30} {doc['scheme']['fund_name']:38} {len(doc['sections'])} sections")
            ok += 1
        except ScrapeError as err:
            print(f"[FAIL] {sid:30} {err}")
            fail += 1
        if i < len(sources) - 1:
            time.sleep(1.0)  # be polite to the server

    print(f"\nDone: {ok} ok, {fail} failed  (fetched_at={fetched_at})  ->  {settings.processed_dir}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
