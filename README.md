# house-sold
A 99acres-style AI property agent for the Indian residential market, driven by a project-local Neurosymbolic Reasoning Engine (NRE).
# House-Sold

A 99acres-style **AI property agent for the Indian residential market**, driven by a project-local **Neurosymbolic Reasoning Engine (NRE)**.

Ask in plain English ("3 BHK villa in Whitefield under 1.5 Cr") and the agent parses the query, plans the right tool calls, fetches listings (live scrape + CSV fallback), and replies with matched properties **and** the locality's median per-sqft price.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Architecture](#architecture)
- [Features](#features)
- [Project layout](#project-layout)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuring `.env`](#configuring-env)
- [Running the app](#running-the-app)
- [Using the UI](#using-the-ui)
- [How the NRE pipeline works](#how-the-nre-pipeline-works)
- [Extending the agent](#extending-the-agent)
- [Troubleshooting](#troubleshooting)
- [Tech stack](#tech-stack)
- [Data sources & disclaimer](#data-sources--disclaimer)

---

## Why this exists

Sites like 99acres or MagicBricks dump 100+ raw filter boxes on you. This project asks one question instead — **"what are you looking for?"** — and lets the agent figure out the rest:

- understand free-text intent (search vs. rate inquiry vs. compare areas vs. advice)
- extract structured slots (city, locality, BHK, budget, property type)
- fetch live listings and compute the area's per-sqft rate
- explain the result in natural language

The "intelligence" is split between a deterministic symbolic core (rules, regex, plan graph) and a neural component (LLM via OpenRouter) — i.e. a **neurosymbolic reasoning engine**.

---

## Architecture

```
                ┌─────────────────────────────────┐
   user query → │  Streamlit UI  (app.py)         │
                │  chat · browse · trace          │
                └────────────────┬────────────────┘
                                 │
                 ┌───────────────▼────────────────┐
                 │ NRE Engine (house_agent/nre/)   │
                 │                                 │
                 │  PARSE      → Slots             │  (regex + LLM)
                 │     ↓                           │
                 │  PLAN       → ordered tool DAG  │  (pure rules)
                 │     ↓                           │
                 │  EXECUTE    → tool outputs      │  (deterministic)
                 │     ↓                           │
                 │  SYNTHESIZE → natural answer    │  (LLM)
                 └───────────────┬────────────────┘
                                 │
                 ┌───────────────▼────────────────┐
                 │ Tool layer (house_agent/tools/)│
                 │                                 │
                 │  search_listings  ── MagicBricks scrape + seed CSV
                 │  get_price_per_sqft           ── median ₹/sqft
                 │  get_locality_info            ── area breakdown
                 │  filter_by_budget             ── post-filter
                 │                                 │
                 │  SQLite cache  (TTL = 1h)       │
                 └─────────────────────────────────┘
```

---

## Features

- **Chat-first UX** — ask in natural English; no filter-grid required.
- **Property types** — Flat / House / Villa / Plot. "Flat" and "Apartment" are aliased.
- **Indian budget input** — accepts `2,00,000`, `5 Lakh`, `5L`, `1.5 Cr`, or raw digits.
- **Dynamic city / locality** — type any Indian city; no hardcoded list.
- **Live data + fallback** — scrapes MagicBricks; falls back to a seed CSV when blocked.
- **Per-sqft area pricing** — median, mean, min/max, sample size for any locality.
- **Locality comparison** — rank all neighbourhoods of a city by rate.
- **Full NRE trace** — inspect slots, plan, tool I/O, and per-stage timings.
- **Configurable model** — any OpenRouter-supported model via `NRE_LLM_MODEL`.
- **No external NRE dependency** — the reasoning engine lives in this repo and is easy to edit.

---

## Project layout

```
house-sold/
├── app.py                          # Streamlit entry point (3 tabs)
├── requirements.txt
├── .env.example                    # template — copy to .env
├── README.md
│
├── house_agent/
│   ├── __init__.py                 # lazy re-exports
│   ├── engine.py                   # thin shim → NRE
│   ├── format.py                   # INR parsing + Indian comma formatting
│   │
│   ├── nre/                        # ─── Neurosymbolic Reasoning Engine ───
│   │   ├── __init__.py
│   │   ├── engine.py               #   orchestrator: PARSE → PLAN → EXECUTE → SYNTHESIZE
│   │   ├── schema.py               #   Pydantic models: Slots, Plan, TurnResult
│   │   ├── llm.py                  #   OpenRouter client (chat_json / chat_text)
│   │   ├── parse.py                #   regex + LLM entity extraction
│   │   ├── plan.py                 #   symbolic rules: intent → tool sequence
│   │   ├── execute.py              #   runs the plan
│   │   └── synthesize.py           #   LLM composes the final reply
│   │
│   ├── tools/                      # ─── Tool layer ───
│   │   ├── __init__.py
│   │   ├── cache.py                #   SQLite TTL cache
│   │   ├── search.py               #   MagicBricks scrape + CSV fallback
│   │   ├── pricing.py              #   per-sqft aggregator + budget filter
│   │   └── locality.py             #   locality breakdown
│   │
│   ├── data/
│   │   └── seed_listings.csv       # ~70-row fallback dataset (Apartment/Villa/House/Plot)
│   │
│   └── ui/                         # reserved for future Streamlit components
│
└── tests/                          # add your tests here
```

---

## Prerequisites

- **Python 3.11+** (tested on 3.13)
- An **OpenRouter API key** — get one at https://openrouter.ai/keys
- Outbound HTTPS access to `openrouter.ai` and (optionally) `magicbricks.com`

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/swapnilbitcoding29-cpu/house-sold.git
cd house-sold

# 2. (Recommended) virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt
```

That's it — there's no separate NRE package to install. The reasoning engine ships inside `house_agent/nre/`.

---

## Configuring `.env`

The app reads environment variables on startup using `python-dotenv`. It looks for `.env` first, then falls back to `.env.example`.

### Step 1 — copy the template

```bash
cp .env.example .env
```

### Step 2 — edit `.env`

Open `.env` in your editor and fill in the values:

```dotenv
# Required ─ the OpenRouter API key (NRE's PARSE and SYNTHESIZE stages call it)
OPENROUTER_API_KEY=sk-or-v1-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# Optional ─ pin the LLM. Default is anthropic/claude-sonnet-4.
# Any model OpenRouter supports works
# (e.g. openai/gpt-4o, anthropic/claude-3.5-sonnet, meta-llama/llama-3.1-70b-instruct).
# NRE_LLM_MODEL=anthropic/claude-sonnet-4

# Optional ─ scraper User-Agent.
# HOUSE_SOLD_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64) ..."

# Optional ─ where the SQLite cache lives. Default: ~/.house_sold_cache.sqlite
# HOUSE_SOLD_CACHE_PATH=/tmp/house_sold_cache.sqlite
```

### Step 3 — getting an OpenRouter key

1. Sign up at https://openrouter.ai
2. Go to https://openrouter.ai/keys → **Create Key**
3. Copy the key (starts with `sk-or-v1-…`) into `OPENROUTER_API_KEY` in your `.env`
4. Add credit to your account if you plan to use paid models. Many models offer free tiers.

### Step 4 — keep secrets out of git

The repo's `.gitignore` excludes `.env`. **Never commit a real key in `.env.example`** — if you accidentally do, rotate the key at https://openrouter.ai/keys immediately.

### Variable reference

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENROUTER_API_KEY` | yes | — | Auth for the PARSE + SYNTHESIZE LLM calls |
| `NRE_LLM_MODEL` | no | `anthropic/claude-sonnet-4` | Which model to use for both stages |
| `HOUSE_SOLD_USER_AGENT` | no | desktop Chrome string | UA sent by the scraper |
| `HOUSE_SOLD_CACHE_PATH` | no | `~/.house_sold_cache.sqlite` | SQLite cache file path |

---

## Running the app

From the project root:

```bash
streamlit run app.py
```

Streamlit prints something like:

```
You can now view your Streamlit app in your browser.
  Local URL: http://localhost:8501
```

Open that URL in your browser. To use a different port:

```bash
streamlit run app.py --server.port 8502
```

To run inside a virtualenv where `streamlit` isn't on `$PATH`:

```bash
python3 -m streamlit run app.py
```

---

## Using the UI

### Sidebar (shared across all tabs)

| Field | Accepts |
|---|---|
| **City** | Any Indian city — `Mumbai`, `Bangalore`, `Pune`, `Hyderabad`, … |
| **Locality** | Substring of a neighbourhood — `Powai`, `Whitefield`, `Baner` |
| **Property type** | `Any` · `Flat` · `House` · `Villa` · `Plot` |
| **BHK** | `Any` or `1`–`5` |
| **Min ₹ / Max ₹** | Raw rupees with Indian or Western commas (`2,00,000` / `200,000`), or suffixes (`5 Lakh`, `1.5 Cr`, `5L`), or plain digits (`20000000`) |

A "Parsed →" line under the budget inputs shows exactly what was captured, so you always know what the agent will see.

### Tab 1 — *Ask the agent*

Free-text chat that runs the full NRE pipeline. Examples:

- *Show me 3 BHK apartments in Powai under 3 Cr*
- *What's the per-sqft rate in Whitefield?*
- *Compare localities in Pune for a 1.5 Cr budget*
- *4 BHK villa in Sarjapur Road below 5 Cr*
- *Plots in Devanahalli under 50,00,000*

### Tab 2 — *Browse & price*

Direct tool calls — **no LLM, no API key required**. Click *Browse listings* in the sidebar. You'll get:

- left: a table of matching listings
- right: the median ₹/sqft for the selected area + a locality breakdown for the city

### Tab 3 — *NRE trace*

After running a chat turn, this tab shows the full pipeline trace:

- parsed slots (intent, city, locality, BHK, budget, property_type)
- the plan (which tools were chosen, in what order, with what arguments)
- raw tool outputs
- per-stage timings in milliseconds

Useful for debugging or for understanding *why* the agent chose what it chose.

---

## How the NRE pipeline works

Each user turn flows through four stages. Each stage is a small, hackable module.

### 1. PARSE — `house_agent/nre/parse.py`

Two passes, regex first (deterministic), then the LLM (covers free-text fields):

| Field | Source | Notes |
|---|---|---|
| `bhk` | regex | matches `3 BHK`, `2 bedroom`, `4 br` |
| `min_price_inr` / `max_price_inr` | regex | Handles `under 3 Cr`, `above 80 lakh`, ranges, and raw Indian-comma amounts like `1,50,00,000` |
| `property_type` | regex | `flat`, `apartment`, `house`, `villa`, `plot`, `bungalow`, … |
| `city`, `locality`, `intent`, `property_type` (fallback) | LLM | JSON output |

Regex wins on numerics; the LLM fills the rest. A `default_city` / `default_locality` / `default_property_type` from the sidebar is passed as **gamma context** so the LLM can use it.

### 2. PLAN — `house_agent/nre/plan.py`

Pure symbolic. Slots → ordered list of `PlanStep(tool, args, rationale)`. Current rules:

| Intent | Tool sequence |
|---|---|
| `search` | `search_listings` (+ `get_price_per_sqft` if a locality was given) |
| `rate` | `get_price_per_sqft` |
| `compare` | `get_locality_info` |
| `advice` | `search_listings` → `get_price_per_sqft` → `get_locality_info` |
| `smalltalk` | (no tools — friendly reply) |

If a required slot is missing (e.g. no city for `search`), the plan stays empty and SYNTHESIZE asks the user for it.

### 3. EXECUTE — `house_agent/nre/execute.py`

Iterates the plan, calls each tool, catches exceptions, and returns a `{tool_name: result}` map. Tool results are cached at the tool boundary (SQLite, 1 h).

### 4. SYNTHESIZE — `house_agent/nre/synthesize.py`

Compacts the tool outputs into a small JSON-ish summary and sends them, along with the original query and the parsed slots, to the LLM with strict instructions (no hallucinated listings, INR formatted as `₹ X Cr` / `₹ Y Lakh`, 3–6 lines). If the LLM call fails, a deterministic template fallback still produces a useful answer.

---

## Extending the agent

### Add a new tool

1. Drop a function into `house_agent/tools/your_tool.py` and re-export from `house_agent/tools/__init__.py`.
2. Register it in `house_agent/nre/execute.py`'s `TOOL_REGISTRY`.
3. Reference it from a `PlanStep` inside `house_agent/nre/plan.py`.

### Add a new intent

1. Add the literal to the `Intent` type in `house_agent/nre/schema.py`.
2. Add a branch in `plan_for()` inside `house_agent/nre/plan.py`.
3. (Optional) Update the LLM system prompt in `house_agent/nre/parse.py` so the model knows when to emit the new intent.

### Swap the LLM model

Set `NRE_LLM_MODEL=<openrouter-model-id>` in `.env`. The OpenRouter wire format is the same for every model, so no code changes are needed.

### Use a different data source

Replace the scrape in `house_agent/tools/search.py`. As long as you return `{"listings": [...], "source": str, "count": int}` with the seed CSV's column shape, everything downstream just works.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Sidebar shows "OPENROUTER_API_KEY missing" | `.env` not found or `OPENROUTER_API_KEY` is blank. Re-check the file. |
| `streamlit: command not found` | Use `python3 -m streamlit run app.py`, or activate the venv. |
| `ModuleNotFoundError: openai` | Run `pip install -r requirements.txt`. |
| Chat reply says "LLM returned non-JSON" | Some models ignore `response_format`. The parser strips ```` ```json ``` ```` fences automatically, but switching to `anthropic/claude-sonnet-4` or `openai/gpt-4o` gives the most reliable JSON output. |
| No live listings, only seed data | MagicBricks blocked the request (UA / captcha). Behaviour is intentional — the agent falls back to the CSV. Verify by setting a different `HOUSE_SOLD_USER_AGENT`. |
| Stale prices after data changes | Clear the cache: `python3 -c "from house_agent.tools.cache import clear; clear()"` |
| Port 8501 is busy | `streamlit run app.py --server.port 8502` |

---

## Tech stack

| Concern | Choice |
|---|---|
| Frontend | Streamlit |
| LLM gateway | OpenRouter (OpenAI-compatible wire format) |
| Default model | `anthropic/claude-sonnet-4` |
| HTTP / scraping | `requests` + `beautifulsoup4` + `lxml` |
| Data wrangling | `pandas` |
| Validation | `pydantic` v2 |
| Cache | SQLite (stdlib) |

---

## Data sources & disclaimer

- **Live data:** MagicBricks public search pages, fetched on demand and cached for 1 hour. Layout changes on the source site can break parsing — the agent falls back to the seed CSV when that happens.
- **Seed data:** `house_agent/data/seed_listings.csv` — a synthetic dataset of ~70 listings across Mumbai, Bangalore, Pune, Gurgaon, Noida, Hyderabad, Chennai, and Kolkata. Prices, builders, and listing IDs are illustrative.
- This project is for **research, demos, and educational use**. It is not affiliated with 99acres or MagicBricks. Verify any price, listing, or rate independently before making a real-world decision.