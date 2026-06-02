"""Listing search: live scrape (best-effort) + CSV fallback.

Contract used by the NRE MATCH primitive:
    search_listings(city: str, locality: str | None = None, bhk: int | None = None,
                    min_price: int | None = None, max_price: int | None = None,
                    limit: int = 25) -> list[dict]

Each listing dict has the same shape as the seed CSV columns so downstream tools
(pricing, ranking) don't care where the row came from.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
import requests
from bs4 import BeautifulSoup

from house_agent.tools import cache

log = logging.getLogger("house_agent.search")

_SEED_CSV = Path(__file__).resolve().parent.parent / "data" / "seed_listings.csv"
_DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT_S = 8


def _ua() -> str:
    return os.environ.get("HOUSE_SOLD_USER_AGENT", _DEFAULT_UA)


def _cache_key(prefix: str, **parts: Any) -> str:
    payload = "|".join(f"{k}={parts[k]}" for k in sorted(parts))
    digest = hashlib.sha1(payload.encode()).hexdigest()[:16]
    return f"{prefix}:{digest}"


# ── Live scrape (best-effort) ────────────────────────────────────────────


def _scrape_magicbricks(city: str, locality: str | None, bhk: int | None) -> list[dict]:
    """Hit MagicBricks search results. Returns [] on any failure — never raises."""
    try:
        q = locality or city
        url = (
            f"https://www.magicbricks.com/property-for-sale/residential-real-estate"
            f"?cityName={quote_plus(city)}&searchType=property&proptype=Multistorey-Apartment"
        )
        if bhk:
            url += f"&bedroom={bhk}"
        if locality:
            url += f"&Locality={quote_plus(locality)}"
        resp = requests.get(url, headers={"User-Agent": _ua()}, timeout=_TIMEOUT_S)
        if resp.status_code != 200 or "captcha" in resp.text.lower():
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("div.mb-srp__card") or soup.select("div.SRPTuple__card")
        out: list[dict] = []
        for card in cards[:30]:
            title = (card.select_one(".mb-srp__card--title") or {}).get_text(strip=True) if hasattr(card.select_one(".mb-srp__card--title"), "get_text") else ""
            price_node = card.select_one(".mb-srp__card__price--amount")
            area_node = card.select_one(".mb-srp__card__summary__list--item")
            link_node = card.select_one("a")
            price_text = price_node.get_text(strip=True) if price_node else ""
            area_text = area_node.get_text(strip=True) if area_node else ""
            out.append(
                {
                    "listing_id": f"MB_{len(out):04d}",
                    "city": city,
                    "locality": locality or "",
                    "bhk": bhk or 0,
                    "property_type": "Apartment",
                    "area_sqft": _parse_sqft(area_text),
                    "price_inr": _parse_price_inr(price_text),
                    "price_per_sqft_inr": None,
                    "status": "Ready to Move",
                    "builder": title,
                    "posted_on": "",
                    "url": (link_node.get("href") if link_node else "") or "",
                    "source": "magicbricks",
                }
            )
        # Fill derived price-per-sqft when both fields are known.
        for r in out:
            if r["area_sqft"] and r["price_inr"]:
                r["price_per_sqft_inr"] = round(r["price_inr"] / r["area_sqft"])
        return [r for r in out if r["price_inr"]]
    except Exception as exc:
        log.warning("magicbricks scrape failed: %s", exc)
        return []


_NUM_RE = re.compile(r"([\d,.]+)")


def _parse_price_inr(text: str) -> int | None:
    """'₹ 1.25 Cr' / '85 Lac' → integer rupees. Returns None if unparseable."""
    if not text:
        return None
    t = text.replace(",", "").lower()
    m = _NUM_RE.search(t)
    if not m:
        return None
    try:
        num = float(m.group(1))
    except ValueError:
        return None
    if "cr" in t:
        return int(num * 10_000_000)
    if "lac" in t or "lakh" in t:
        return int(num * 100_000)
    return int(num)


def _parse_sqft(text: str) -> int | None:
    if not text:
        return None
    m = _NUM_RE.search(text.replace(",", ""))
    if not m:
        return None
    try:
        return int(float(m.group(1)))
    except ValueError:
        return None


# ── CSV fallback (always works) ──────────────────────────────────────────


def _load_seed() -> pd.DataFrame:
    return pd.read_csv(_SEED_CSV)


# "Flat" and "Apartment" mean the same thing in Indian listings. Canonicalize
# both directions so users can pick either label in the UI.
_PROPERTY_TYPE_ALIASES = {
    "flat": {"apartment", "flat"},
    "apartment": {"apartment", "flat"},
    "house": {"house", "independent house"},
    "villa": {"villa", "independent villa"},
    "plot": {"plot", "land"},
}


def _property_type_match_set(value: str | None) -> set[str] | None:
    if not value:
        return None
    key = value.strip().lower()
    return _PROPERTY_TYPE_ALIASES.get(key, {key})


def _filter_seed(
    df: pd.DataFrame,
    city: str,
    locality: str | None,
    bhk: int | None,
    min_price: int | None,
    max_price: int | None,
    property_type: str | None,
) -> pd.DataFrame:
    mask = df["city"].str.lower() == city.lower()
    if locality:
        mask &= df["locality"].str.lower().str.contains(locality.lower(), na=False)
    if bhk:
        mask &= df["bhk"] == bhk
    if min_price:
        mask &= df["price_inr"] >= min_price
    if max_price:
        mask &= df["price_inr"] <= max_price
    if (allowed := _property_type_match_set(property_type)) is not None:
        mask &= df["property_type"].str.lower().isin(allowed)
    return df[mask].copy()


# ── Public tool ──────────────────────────────────────────────────────────


def search_listings(
    city: str,
    locality: str | None = None,
    bhk: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    property_type: str | None = None,
    limit: int = 25,
) -> dict:
    """Find ready-to-sell listings. Live scrape → CSV fallback.

    Returns:
        {"listings": [...], "source": "live" | "fallback" | "mixed", "count": int}
    """
    if not city:
        return {"listings": [], "source": "none", "count": 0, "error": "city is required"}

    key = _cache_key(
        "search",
        city=city, locality=locality, bhk=bhk,
        min_p=min_price, max_p=max_price, ptype=(property_type or "").lower(),
    )
    cached = cache.get(key)
    if cached is not None:
        cached_clipped = cached["listings"][:limit]
        return {**cached, "listings": cached_clipped, "count": len(cached_clipped)}

    live = _scrape_magicbricks(city, locality, bhk)
    if min_price or max_price:
        live = [
            r for r in live
            if r.get("price_inr")
            and (min_price is None or r["price_inr"] >= min_price)
            and (max_price is None or r["price_inr"] <= max_price)
        ]
    if (allowed := _property_type_match_set(property_type)) is not None:
        live = [r for r in live if (r.get("property_type") or "").lower() in allowed]

    fallback = _filter_seed(
        _load_seed(), city, locality, bhk, min_price, max_price, property_type
    ).to_dict(orient="records")
    for r in fallback:
        r["source"] = "seed"

    combined = live + fallback
    if not combined:
        result = {"listings": [], "source": "none", "count": 0}
    elif live and fallback:
        result = {"listings": combined, "source": "mixed", "count": len(combined)}
    elif live:
        result = {"listings": combined, "source": "live", "count": len(combined)}
    else:
        result = {"listings": combined, "source": "fallback", "count": len(combined)}

    cache.put(key, result, ttl=60 * 60)
    return {**result, "listings": result["listings"][:limit], "count": min(limit, result["count"])}
