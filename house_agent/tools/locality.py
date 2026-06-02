"""Locality summary tool: distinct localities + average rate for a city.

Useful as a discovery step when the user asks "what areas are available in X?"
"""

from __future__ import annotations

from statistics import median

from house_agent.tools.search import search_listings


def get_locality_info(city: str) -> dict:
    """Return the distinct localities in a city with their median rate.

    Returns:
        {"city": str, "localities": [{"name", "sample_size",
          "median_inr_per_sqft", "min_price_inr", "max_price_inr"}, ...]}
    """
    res = search_listings(city=city, limit=500)
    by_locality: dict[str, list[dict]] = {}
    for r in res["listings"]:
        loc = (r.get("locality") or "").strip()
        if not loc:
            continue
        by_locality.setdefault(loc, []).append(r)

    rows = []
    for loc, items in by_locality.items():
        rates = [i["price_per_sqft_inr"] for i in items if i.get("price_per_sqft_inr")]
        prices = [i["price_inr"] for i in items if i.get("price_inr")]
        rows.append(
            {
                "name": loc,
                "sample_size": len(items),
                "median_inr_per_sqft": int(median(rates)) if rates else 0,
                "min_price_inr": int(min(prices)) if prices else 0,
                "max_price_inr": int(max(prices)) if prices else 0,
            }
        )
    rows.sort(key=lambda r: r["median_inr_per_sqft"], reverse=True)
    return {"city": city, "localities": rows, "source": res.get("source")}
