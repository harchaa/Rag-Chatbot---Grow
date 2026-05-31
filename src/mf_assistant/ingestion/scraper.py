"""Fetch and extract structured scheme data from Groww scheme pages.

Groww is a Next.js (Pages Router) app: each scheme page embeds a clean JSON blob in a
``<script id="__NEXT_DATA__">`` tag, so we parse that instead of scraping rendered HTML.
The scheme facts live at ``props.pageProps.mfServerSideData``.
"""

from __future__ import annotations

import json
import time

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class ScrapeError(RuntimeError):
    """Raised when a page cannot be fetched or its structure is unexpected."""


def fetch_scheme_data(url: str, *, timeout: int = 30, retries: int = 2) -> dict:
    """Return the raw ``mfServerSideData`` dict for a Groww scheme URL."""
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return _extract(resp.text, url)
        except (requests.RequestException, ScrapeError) as err:
            last_err = err
            if attempt < retries:
                time.sleep(2 * attempt)  # simple backoff
    raise ScrapeError(f"Failed to fetch {url}: {last_err}")


def _extract(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag is None or not tag.string:
        raise ScrapeError(f"No __NEXT_DATA__ blob found at {url}")
    try:
        ssd = json.loads(tag.string)["props"]["pageProps"]["mfServerSideData"]
    except (json.JSONDecodeError, KeyError, TypeError) as err:
        raise ScrapeError(f"Unexpected page structure at {url}: {err}") from err
    if not isinstance(ssd, dict) or "fund_name" not in ssd:
        raise ScrapeError(f"mfServerSideData missing scheme facts at {url}")
    return ssd
