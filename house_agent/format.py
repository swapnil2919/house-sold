"""INR parsing + Indian-style number formatting.

Used by the Streamlit sidebar (raw text input) and the synthesize stage
(rendering tool outputs back to the user).

Accepts: "2,00,000", "200,000", "5 lakh", "5L", "1.5 cr", "20000000".
Renders: "2,00,000" (Indian grouping), "₹ 2 Cr", "₹ 50 Lakh".
"""

from __future__ import annotations

import re

_SUFFIX_CR = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:cr|crore|crores)\s*$", re.IGNORECASE)
_SUFFIX_LAKH = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs|l)\s*$", re.IGNORECASE)
_DIGITS_ONLY = re.compile(r"^\d+$")


def parse_inr(text: str | None) -> int | None:
    """Parse a user-entered budget into INR (int). Returns None on empty/invalid."""
    if not text:
        return None
    s = str(text).strip().replace("₹", "").replace(" ", " ").strip()
    if not s:
        return None

    # Suffix forms first (so "1.5 Cr" doesn't get mis-parsed as "1.5").
    if m := _SUFFIX_CR.match(s):
        return int(float(m.group(1)) * 10_000_000)
    if m := _SUFFIX_LAKH.match(s):
        return int(float(m.group(1)) * 100_000)

    # Raw digits — strip Indian or Western commas.
    bare = s.replace(",", "")
    if _DIGITS_ONLY.match(bare):
        return int(bare)
    try:
        # Allow decimals like "20000000.0".
        return int(float(bare))
    except ValueError:
        return None


def format_inr_indian(n: int | None) -> str:
    """Render an integer in Indian comma grouping: 200000 → '2,00,000'."""
    if n is None:
        return ""
    s = str(int(n))
    if len(s) <= 3:
        return s
    last3, rest = s[-3:], s[:-3]
    # Group `rest` in chunks of 2 from the right.
    pieces = []
    while len(rest) > 2:
        pieces.append(rest[-2:])
        rest = rest[:-2]
    pieces.append(rest)
    return ",".join(reversed(pieces)) + "," + last3


def format_inr_short(n: int | None) -> str:
    """Short human form: '₹ 2 Cr', '₹ 50 Lakh', or '₹ 12,500'."""
    if not n:
        return ""
    if n >= 10_000_000:
        v = n / 10_000_000
        return f"₹ {v:.2f} Cr" if v % 1 else f"₹ {int(v)} Cr"
    if n >= 100_000:
        v = n / 100_000
        return f"₹ {v:.1f} Lakh" if v % 1 else f"₹ {int(v)} Lakh"
    return f"₹ {format_inr_indian(n)}"
