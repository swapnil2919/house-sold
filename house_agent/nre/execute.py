"""EXECUTE stage: run the plan's tool steps and collect outputs."""

from __future__ import annotations

import logging
from typing import Any, Callable

from house_agent.tools import (
    filter_by_budget,
    get_locality_info,
    get_price_per_sqft,
    search_listings,
)
from house_agent.nre.schema import Plan

log = logging.getLogger("house_agent.nre.execute")

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "search_listings": search_listings,
    "get_price_per_sqft": get_price_per_sqft,
    "get_locality_info": get_locality_info,
    "filter_by_budget": filter_by_budget,
}


def execute(plan: Plan) -> dict[str, Any]:
    """Run each step in order. Returns {tool_name: result} (last-write-wins per tool)."""
    out: dict[str, Any] = {}
    for step in plan.steps:
        fn = TOOL_REGISTRY.get(step.tool)
        if fn is None:
            log.warning("Unknown tool %s — skipping", step.tool)
            out[step.tool] = {"error": f"unknown tool {step.tool!r}"}
            continue
        try:
            cleaned = {k: v for k, v in step.args.items() if v is not None}
            result = fn(**cleaned)
        except Exception as exc:
            log.exception("Tool %s failed", step.tool)
            result = {"error": str(exc)}
        out[step.tool] = result
    return out
