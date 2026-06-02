"""Pricing tools: per-sqft rate for a locality + budget filtering.

`get_price_per_sqft` aggregates listings (live + seed) to compute a
median/mean rate for a city or city+locality pair. It's the answer to
"what's the rate in Powai?"
"""

from __future__ import annotations

from statistics import mean, median
from typing import Any

from house_agent.tools.search import search_listings


def get_price_per_sqft(city: str, locality: str | None = None) -> dict:
    """Return aggregated price-per-sqft (INR) for the given area.

    Returns:
        {"city": str, "locality": str | None, "median_inr_per_sqft": int,
         "mean_inr_per_sqft": int, "sample_size": int,
         "min_inr_per_sqft": int, "max_inr_per_sqft": int}
    """
    res = search_listings(city=city, locality=locality, limit=200)
    rates = [
        r["price_per_sqft_inr"]
        for r in res["listings"]
        if r.get("price_per_sqft_inr")
    ]
    if not rates:
        return {
            "city": city,
            "locality": locality,
            "median_inr_per_sqft": 0,
            "mean_inr_per_sqft": 0,
            "sample_size": 0,
            "min_inr_per_sqft": 0,
            "max_inr_per_sqft": 0,
            "note": "no listings found for this area",
        }
    return {
        "city": city,
        "locality": locality,
        "median_inr_per_sqft": int(median(rates)),
        "mean_inr_per_sqft": int(mean(rates)),
        "sample_size": len(rates),
        "min_inr_per_sqft": int(min(rates)),
        "max_inr_per_sqft": int(max(rates)),
        "source": res.get("source"),
    }


def filter_by_budget(
    listings: list[dict[str, Any]],
    min_price: int | None = None,
    max_price: int | None = None,
) -> dict:
    """Filter a listings list by INR budget. Pure function, no I/O."""
    out = []
    for r in listings or []:
        p = r.get("price_inr")
        if p is None:
            continue
        if min_price is not None and p < min_price:
            continue
        if max_price is not None and p > max_price:
            continue
        out.append(r)
    return {"listings": out, "count": len(out)}
