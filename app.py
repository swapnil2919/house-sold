"""House-Sold — Streamlit frontend for the project-local NRE property agent.

Run:
    cp .env.example .env  # fill OPENROUTER_API_KEY (or keep it in .env.example)
    pip install -r requirements.txt
    streamlit run app.py
"""

from __future__ import annotations

import os
import traceback
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from house_agent.format import format_inr_indian, format_inr_short, parse_inr

load_dotenv()
load_dotenv(".env.example")  # fallback so a key in the template still works

st.set_page_config(
    page_title="House-Sold • NRE Property Agent",
    page_icon="🏠",
    layout="wide",
)


# ── Lazy imports (so the page renders even if the LLM stack is mis-configured) ──


def _lazy_engine():
    from house_agent.nre import run_turn  # noqa: WPS433
    return run_turn


def _lazy_tools():
    from house_agent.tools import (  # noqa: WPS433
        get_locality_info,
        get_price_per_sqft,
        search_listings,
    )
    return search_listings, get_price_per_sqft, get_locality_info


# ── Sidebar ──────────────────────────────────────────────────────────────

st.sidebar.title("🏠 House-Sold")
st.sidebar.caption("99acres-style search powered by a local Neurosymbolic Reasoning Engine.")

city = st.sidebar.text_input("City", value="Mumbai", help="Any Indian city.")
locality = st.sidebar.text_input("Locality (optional)", value="", placeholder="e.g. Powai, Whitefield, Baner")

_PTYPE_OPTIONS = ["Any", "Flat", "House", "Villa", "Plot"]
property_type_label = st.sidebar.selectbox(
    "Property type",
    options=_PTYPE_OPTIONS,
    index=0,
    help="Flat = Apartment. Plot = land only.",
)
property_type = None if property_type_label == "Any" else property_type_label

bhk = st.sidebar.selectbox("BHK", options=[None, 1, 2, 3, 4, 5], index=0,
                           format_func=lambda v: "Any" if v is None else f"{v} BHK")

st.sidebar.caption("💰 Budget — enter raw rupees (e.g. `2,00,000`), or `5 Lakh`, or `1.5 Cr`")
col_a, col_b = st.sidebar.columns(2)
with col_a:
    min_price_raw = st.text_input("Min ₹", value="", placeholder="e.g. 50,00,000")
with col_b:
    max_price_raw = st.text_input("Max ₹", value="", placeholder="e.g. 1.5 Cr")

min_price_inr = parse_inr(min_price_raw)
max_price_inr = parse_inr(max_price_raw)

# Live echo so users see exactly what was parsed.
_min_echo = format_inr_indian(min_price_inr) if min_price_inr else "—"
_max_echo = format_inr_indian(max_price_inr) if max_price_inr else "—"
_min_short = format_inr_short(min_price_inr) if min_price_inr else ""
_max_short = format_inr_short(max_price_inr) if max_price_inr else ""
st.sidebar.caption(
    f"Parsed → Min: **₹ {_min_echo}**" + (f" ({_min_short})" if _min_short else "")
    + f" · Max: **₹ {_max_echo}**" + (f" ({_max_short})" if _max_short else "")
)
if (min_price_raw and min_price_inr is None) or (max_price_raw and max_price_inr is None):
    st.sidebar.warning("One of the budgets couldn't be parsed — try `5 Lakh` or `2,00,000`.")
if min_price_inr and max_price_inr and min_price_inr > max_price_inr:
    st.sidebar.warning("Min budget is higher than Max — swap them?")

st.sidebar.divider()
if os.environ.get("OPENROUTER_API_KEY"):
    st.sidebar.success("OPENROUTER_API_KEY loaded ✓")
else:
    st.sidebar.error("OPENROUTER_API_KEY missing. Chat will degrade; Browse tab still works.")

run_browse = st.sidebar.button("🔍 Browse listings", use_container_width=True)


def _budget_inr() -> tuple[int | None, int | None]:
    return min_price_inr, max_price_inr


# ── Tabs ─────────────────────────────────────────────────────────────────

tab_chat, tab_browse, tab_trace = st.tabs(["💬 Ask the agent", "📋 Browse & price", "🔬 NRE trace"])


# ── Chat tab: full NRE pipeline ──────────────────────────────────────────

with tab_chat:
    st.subheader("Ask anything about houses ready to be sold")
    st.caption(
        "Examples: *Show me 3 BHK in Powai under 3 Cr* · "
        "*What's the per-sqft rate in Whitefield?* · "
        "*Which areas in Pune are best for a 1.5 Cr budget?*"
    )

    if "history" not in st.session_state:
        st.session_state.history = []

    for entry in st.session_state.history:
        with st.chat_message(entry["role"]):
            st.markdown(entry["content"])
            if entry.get("listings"):
                st.dataframe(pd.DataFrame(entry["listings"]),
                             use_container_width=True, hide_index=True)

    prompt = st.chat_input("What kind of house are you looking for?")
    if prompt:
        st.session_state.history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("NRE pipeline: PARSE → PLAN → EXECUTE → SYNTHESIZE…"):
                try:
                    run_turn = _lazy_engine()
                    gamma: dict[str, Any] = {}
                    if city:
                        gamma["default_city"] = city
                    if locality:
                        gamma["default_locality"] = locality
                    if property_type:
                        gamma["default_property_type"] = property_type
                    result = run_turn(prompt, gamma=gamma)
                except Exception as exc:
                    st.error(f"Agent failed: {exc}")
                    with st.expander("Traceback"):
                        st.code(traceback.format_exc())
                    st.session_state.history.append({"role": "assistant", "content": f"⚠️ {exc}"})
                    result = None

            if result:
                st.session_state.last_trace = result.model_dump()
                st.markdown(result.answer)

                if result.listings:
                    st.markdown("**Matching listings**")
                    df = pd.DataFrame(result.listings)
                    cols = [c for c in [
                        "listing_id", "locality", "bhk", "area_sqft",
                        "price_inr", "price_per_sqft_inr", "builder",
                        "status", "url",
                    ] if c in df.columns]
                    st.dataframe(df[cols], use_container_width=True, hide_index=True)

                if result.price_summary and result.price_summary.get("sample_size"):
                    p = result.price_summary
                    target = p.get("locality") or p.get("city")
                    st.metric(
                        f"Median ₹/sqft in {target}",
                        f"₹{p['median_inr_per_sqft']:,}",
                        delta=f"n={p['sample_size']}",
                    )

                if result.locality_breakdown:
                    with st.expander("Locality breakdown"):
                        st.dataframe(pd.DataFrame(result.locality_breakdown),
                                     use_container_width=True, hide_index=True)

                st.session_state.history.append(
                    {"role": "assistant", "content": result.answer, "listings": result.listings}
                )


# ── Browse tab: direct tools, no LLM needed ──────────────────────────────

with tab_browse:
    st.subheader("Browse listings & per-sqft rates")
    st.caption("Direct tool calls — no LLM. Useful for raw data.")

    min_p, max_p = _budget_inr()

    if run_browse or st.session_state.get("browse_done"):
        st.session_state.browse_done = True
        search_listings, get_price_per_sqft, get_locality_info = _lazy_tools()

        col_l, col_r = st.columns([2, 1])

        with col_l:
            st.markdown("### 🏘️ Matching listings")
            with st.spinner("Searching…"):
                res = search_listings(
                    city=city, locality=locality or None, bhk=bhk,
                    min_price=min_p, max_price=max_p,
                    property_type=property_type, limit=50,
                )
            st.caption(f"Source: **{res['source']}** • {res['count']} listings")
            if res["listings"]:
                df = pd.DataFrame(res["listings"])
                cols = [c for c in [
                    "listing_id", "city", "locality", "bhk", "area_sqft",
                    "price_inr", "price_per_sqft_inr", "status", "builder",
                    "posted_on", "source", "url",
                ] if c in df.columns]
                st.dataframe(df[cols], use_container_width=True, hide_index=True)
            else:
                st.info("No listings matched. Try widening your filters.")

        with col_r:
            st.markdown("### 💰 Area rate")
            with st.spinner("Aggregating…"):
                price = get_price_per_sqft(city=city, locality=locality or None)
            if price["sample_size"]:
                target = locality or city
                st.metric(
                    f"Median ₹/sqft in {target}",
                    f"₹{price['median_inr_per_sqft']:,}",
                    delta=f"sample n={price['sample_size']}",
                )
                st.caption(
                    f"Mean ₹{price['mean_inr_per_sqft']:,} • "
                    f"Range ₹{price['min_inr_per_sqft']:,}–₹{price['max_inr_per_sqft']:,}"
                )
            else:
                st.warning("No rate data for this area yet.")

            st.markdown("### 🗺️ Localities in city")
            with st.spinner("Loading localities…"):
                loc_info = get_locality_info(city=city)
            if loc_info["localities"]:
                st.dataframe(pd.DataFrame(loc_info["localities"]),
                             use_container_width=True, hide_index=True)
            else:
                st.info(f"No locality data for {city}.")
    else:
        st.info("Set filters in the sidebar and click **Browse listings**.")


# ── Trace tab ────────────────────────────────────────────────────────────

with tab_trace:
    st.subheader("Last NRE turn — full trace")
    st.caption("PARSE (slots) → PLAN (steps) → EXECUTE (tools) → SYNTHESIZE (answer)")
    trace = st.session_state.get("last_trace")
    if not trace:
        st.info("Run a chat query first to see the pipeline trace here.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Parsed slots**")
            st.json(trace["slots"])
        with col2:
            st.markdown("**Plan**")
            st.json(trace["plan"])
        st.markdown("**Tool outputs**")
        st.json(trace["tool_outputs"])
        st.markdown("**Stage timings**")
        timings = [
            {"stage": e["stage"], **e["detail"]}
            for e in trace["trace"]["entries"]
        ]
        st.dataframe(pd.DataFrame(timings), use_container_width=True, hide_index=True)
