"""SYNTHESIZE stage: LLM composes the final natural-language answer.

We give the LLM:
  - the original user query
  - the parsed slots
  - a compact summary of tool outputs (clipped to keep prompt small)
and ask for a concise, friendly reply suitable for a chat UI.

If the LLM call fails we fall back to a deterministic template — the agent
still produces a useful answer.
"""

from __future__ import annotations

import logging
from typing import Any

from house_agent.nre.llm import chat_text
from house_agent.nre.schema import Plan, Slots

log = logging.getLogger("house_agent.nre.synthesize")


_SYSTEM = """You are a property advisor for an Indian real-estate agent (99acres-style).
Compose a concise, friendly reply (3-6 lines, plain Markdown, no headings) using ONLY the tool outputs provided.

Rules:
- Format INR as "₹ X Cr" or "₹ Y Lakh", never raw integers.
- Cite the per-sqft rate when relevant.
- If listings exist, mention how many were found and a couple of standouts (by price/sqft fit).
- If no city was provided, ask the user for one — don't fabricate.
- Never invent listing IDs, prices, or builders not present in the tool outputs.
"""


def _format_inr(value: int | None) -> str | None:
    if not value:
        return None
    if value >= 10_000_000:
        return f"₹ {value / 10_000_000:.2f} Cr"
    return f"₹ {value / 100_000:.1f} Lakh"


def _summarize_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    """Clip tool outputs to a prompt-friendly subset."""
    summary: dict[str, Any] = {}
    if listings_res := outputs.get("search_listings"):
        listings = listings_res.get("listings", [])[:8]
        summary["search_listings"] = {
            "count": listings_res.get("count"),
            "source": listings_res.get("source"),
            "examples": [
                {
                    "locality": r.get("locality"),
                    "bhk": r.get("bhk"),
                    "area_sqft": r.get("area_sqft"),
                    "price": _format_inr(r.get("price_inr")),
                    "rate_inr_per_sqft": r.get("price_per_sqft_inr"),
                    "builder": r.get("builder"),
                }
                for r in listings
            ],
        }
    if price := outputs.get("get_price_per_sqft"):
        summary["get_price_per_sqft"] = {
            "city": price.get("city"),
            "locality": price.get("locality"),
            "median_inr_per_sqft": price.get("median_inr_per_sqft"),
            "sample_size": price.get("sample_size"),
            "range": [price.get("min_inr_per_sqft"), price.get("max_inr_per_sqft")],
        }
    if loc := outputs.get("get_locality_info"):
        summary["get_locality_info"] = {
            "city": loc.get("city"),
            "top_localities": loc.get("localities", [])[:6],
        }
    return summary


def _fallback(query: str, slots: Slots, outputs: dict[str, Any]) -> str:
    """Deterministic template used when the LLM stage is unavailable."""
    parts: list[str] = []
    if listings_res := outputs.get("search_listings"):
        count = listings_res.get("count", 0)
        parts.append(f"Found **{count}** listings (source: {listings_res.get('source')}).")
    if price := outputs.get("get_price_per_sqft"):
        if price.get("sample_size"):
            target = price.get("locality") or price.get("city")
            parts.append(
                f"Median rate in {target}: **₹{price['median_inr_per_sqft']:,}/sqft** "
                f"(n={price['sample_size']})."
            )
    if loc := outputs.get("get_locality_info"):
        rows = loc.get("localities", [])[:5]
        parts.append("Top localities: " + ", ".join(r["name"] for r in rows))
    if not parts:
        if not slots.city:
            return "Which city should I search in?"
        return "I couldn't find matching listings for those filters."
    return " ".join(parts)


def synthesize(
    query: str,
    slots: Slots,
    plan: Plan,
    outputs: dict[str, Any],
) -> str:
    if plan.intent == "smalltalk":
        return "Hi! Tell me a city and what kind of place you want — e.g. *3 BHK in Powai under 3 Cr*."
    if not slots.city:
        return "I need a city to start. Which city are you looking in?"

    summary = _summarize_outputs(outputs)
    user_msg = (
        f"User query: {query}\n"
        f"Parsed slots: {slots.model_dump()}\n"
        f"Plan intent: {plan.intent}\n"
        f"Tool outputs (compact): {summary}"
    )
    try:
        return chat_text(_SYSTEM, user_msg, temperature=0.3, max_tokens=500)
    except Exception as exc:
        log.warning("Synthesis LLM failed, using fallback: %s", exc)
        return _fallback(query, slots, outputs)
