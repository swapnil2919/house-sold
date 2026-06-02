"""PARSE stage: regex (symbolic) + LLM (neural) → Slots.

Strategy:
- Run regex extractors first — they're cheap, deterministic, and catch the
  numeric stuff (BHK, budget, area) reliably.
- Call the LLM to fill remaining fields (city, locality, intent), passing
  the regex hits as a hint so the LLM doesn't override them.
- Merge with regex winning on the numeric fields and LLM winning on the
  free-text fields (city/locality/intent).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from house_agent.nre.llm import chat_json
from house_agent.nre.schema import Slots

log = logging.getLogger("house_agent.nre.parse")


_BHK_RE = re.compile(r"\b(\d)\s*(?:bhk|bedroom|bedrooms|br)\b", re.IGNORECASE)
_PROPERTY_TYPE_RE = re.compile(
    r"\b(villa|villas|bungalow|house|houses|independent\s+house|"
    r"plot|plots|land|flat|flats|apartment|apartments)\b",
    re.IGNORECASE,
)
_PTYPE_CANON = {
    "villa": "Villa", "villas": "Villa", "bungalow": "Villa",
    "house": "House", "houses": "House", "independent house": "House",
    "plot": "Plot", "plots": "Plot", "land": "Plot",
    "flat": "Flat", "flats": "Flat", "apartment": "Apartment", "apartments": "Apartment",
}
_CR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:cr|crore|crores)", re.IGNORECASE)
_LAKH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs|l)\b", re.IGNORECASE)
_RANGE_RE = re.compile(
    r"(?:between|from|in)\s+(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)\s*(cr|crore|lakh|lac|lakhs|lacs)",
    re.IGNORECASE,
)
_UNDER_RE = re.compile(
    r"(?:under|below|less than|<=|<)\s*(\d+(?:\.\d+)?)\s*(cr|crore|lakh|lac|lakhs|lacs)",
    re.IGNORECASE,
)
_OVER_RE = re.compile(
    r"(?:above|over|more than|>=|>)\s*(\d+(?:\.\d+)?)\s*(cr|crore|lakh|lac|lakhs|lacs)",
    re.IGNORECASE,
)
_UNDER_RAW_RE = re.compile(
    r"(?:under|below|less than|<=|<)\s*(?:rs\.?|₹|inr)?\s*([\d,]{4,})\b",
    re.IGNORECASE,
)
_OVER_RAW_RE = re.compile(
    r"(?:above|over|more than|>=|>)\s*(?:rs\.?|₹|inr)?\s*([\d,]{4,})\b",
    re.IGNORECASE,
)


def _unit_to_inr(value: float, unit: str) -> int:
    unit = unit.lower()
    if unit.startswith("cr"):
        return int(value * 10_000_000)
    return int(value * 100_000)  # lakh


def regex_pass(text: str) -> dict[str, Any]:
    """Run the symbolic regex extractors. Returns partial-slot dict."""
    out: dict[str, Any] = {}
    if m := _BHK_RE.search(text):
        out["bhk"] = int(m.group(1))
    if m := _PROPERTY_TYPE_RE.search(text):
        token = " ".join(m.group(1).lower().split())
        out["property_type"] = _PTYPE_CANON.get(token, token.title())

    if m := _RANGE_RE.search(text):
        lo, hi, unit = m.group(1), m.group(2), m.group(3)
        out["min_price_inr"] = _unit_to_inr(float(lo), unit)
        out["max_price_inr"] = _unit_to_inr(float(hi), unit)
    else:
        if m := _UNDER_RE.search(text):
            out["max_price_inr"] = _unit_to_inr(float(m.group(1)), m.group(2))
        elif m := _UNDER_RAW_RE.search(text):
            digits = m.group(1).replace(",", "")
            if digits.isdigit() and int(digits) >= 100_000:
                out["max_price_inr"] = int(digits)
        if m := _OVER_RE.search(text):
            out["min_price_inr"] = _unit_to_inr(float(m.group(1)), m.group(2))
        elif m := _OVER_RAW_RE.search(text):
            digits = m.group(1).replace(",", "")
            if digits.isdigit() and int(digits) >= 100_000:
                out["min_price_inr"] = int(digits)
        # Bare "3 cr" or "85 lakh" mentioned alone → treat as upper bound only
        # if no explicit qualifier matched.
        if "max_price_inr" not in out and "min_price_inr" not in out:
            if m := _CR_RE.search(text):
                out["max_price_inr"] = _unit_to_inr(float(m.group(1)), "cr")
            elif m := _LAKH_RE.search(text):
                out["max_price_inr"] = _unit_to_inr(float(m.group(1)), "lakh")
    return out


_PARSE_SYSTEM = """You are the PARSE stage of a neurosymbolic agent for Indian residential property.
Extract structured slots from the user query and return strict JSON.

Schema:
{
  "intent": "search" | "rate" | "compare" | "advice" | "smalltalk",
  "city": <string|null>,        // Indian city name in canonical form (e.g. "Mumbai", "Bangalore", "Pune", "Gurgaon")
  "locality": <string|null>,    // sub-area / neighbourhood (e.g. "Powai", "Whitefield")
  "property_type": <string|null>  // "Apartment" | "Villa" | "Plot" | null
}

Intent rules:
- "search": user wants a list of properties matching criteria
- "rate":   user asks about price per sqft / market rate for an area
- "compare":user wants to compare localities within a city
- "advice": user asks "where should I buy", "best area for X", investment questions
- "smalltalk": greetings, off-topic, vague chat

Hints from regex (DO NOT override these — they are authoritative):
- BHK, min_price_inr, max_price_inr have already been extracted.

If a default city is provided in the user message context, use it when the query has none.
Return JSON only. No commentary."""


def llm_pass(query: str, regex_slots: dict[str, Any], gamma: dict[str, Any]) -> dict[str, Any]:
    hints = {**regex_slots}
    user_msg_parts = [f"Query: {query}"]
    if hints:
        user_msg_parts.append(f"Regex-extracted (authoritative): {hints}")
    if gamma:
        relevant_gamma = {k: gamma[k] for k in ("default_city", "default_locality") if gamma.get(k)}
        if relevant_gamma:
            user_msg_parts.append(f"Conversation context: {relevant_gamma}")
    try:
        return chat_json(_PARSE_SYSTEM, "\n".join(user_msg_parts), max_tokens=300) or {}
    except Exception as exc:
        log.warning("LLM parse failed, regex-only: %s", exc)
        return {}


def parse(query: str, gamma: dict[str, Any] | None = None) -> Slots:
    gamma = gamma or {}
    regex_slots = regex_pass(query)
    llm_slots = llm_pass(query, regex_slots, gamma)

    # Merge: regex wins on numeric fields, LLM wins on free-text.
    merged: dict[str, Any] = {
        "intent": llm_slots.get("intent") or "search",
        "city": llm_slots.get("city") or gamma.get("default_city"),
        "locality": llm_slots.get("locality") or gamma.get("default_locality"),
        "property_type": (
            llm_slots.get("property_type") or gamma.get("default_property_type")
        ),
        **regex_slots,  # regex wins on numerics; property_type re-added below
    }
    # Regex property_type wins over LLM/gamma when present (deterministic).
    if "property_type" in regex_slots:
        merged["property_type"] = regex_slots["property_type"]
    # Coerce stray empty strings.
    for k in ("city", "locality", "property_type"):
        if isinstance(merged.get(k), str) and not merged[k].strip():
            merged[k] = None
    return Slots(**merged)
