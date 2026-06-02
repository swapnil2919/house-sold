"""NRE engine — orchestrates PARSE → PLAN → EXECUTE → SYNTHESIZE."""

from __future__ import annotations

import logging
import time
from typing import Any

from house_agent.nre.execute import execute as execute_plan
from house_agent.nre.parse import parse
from house_agent.nre.plan import plan_for
from house_agent.nre.schema import Trace, TurnResult
from house_agent.nre.synthesize import synthesize

log = logging.getLogger("house_agent.nre.engine")


class NREEngine:
    """Stateless orchestrator. Construct once; call `.run(query)` per turn."""

    def run(self, query: str, *, gamma: dict[str, Any] | None = None) -> TurnResult:
        gamma = gamma or {}
        trace = Trace()

        t0 = time.perf_counter()
        slots = parse(query, gamma=gamma)
        trace.add("parse", slots=slots.model_dump(), ms=int((time.perf_counter() - t0) * 1000))
        log.info("PARSE  → %s", slots.model_dump())

        t0 = time.perf_counter()
        plan = plan_for(slots)
        trace.add("plan", plan=plan.model_dump(), ms=int((time.perf_counter() - t0) * 1000))
        log.info("PLAN   → intent=%s steps=%s", plan.intent, [s.tool for s in plan.steps])

        t0 = time.perf_counter()
        outputs = execute_plan(plan)
        trace.add(
            "execute",
            tools=list(outputs.keys()),
            ms=int((time.perf_counter() - t0) * 1000),
        )
        log.info("EXECUTE → tools=%s", list(outputs.keys()))

        t0 = time.perf_counter()
        answer = synthesize(query, slots, plan, outputs)
        trace.add("synthesize", chars=len(answer), ms=int((time.perf_counter() - t0) * 1000))

        listings = (outputs.get("search_listings") or {}).get("listings", []) or []
        price_summary = outputs.get("get_price_per_sqft")
        locality_breakdown = (outputs.get("get_locality_info") or {}).get("localities")

        return TurnResult(
            answer=answer,
            slots=slots,
            plan=plan,
            tool_outputs=outputs,
            listings=listings,
            price_summary=price_summary,
            locality_breakdown=locality_breakdown,
            trace=trace,
        )


_engine_singleton: NREEngine | None = None


def run_turn(query: str, *, gamma: dict[str, Any] | None = None) -> TurnResult:
    """Module-level convenience: lazy-init singleton + run one turn."""
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = NREEngine()
    return _engine_singleton.run(query, gamma=gamma)
