"""Top-level engine — thin re-export of the local NRE layer.

This used to wire an external NRE package; we now use the project-local NRE
layer in `house_agent.nre`. Keeping this thin module so old imports keep
working.
"""

from __future__ import annotations

from typing import Any

from house_agent.nre import NREEngine, run_turn as _run_turn


def build_house_agent_engine() -> NREEngine:
    return NREEngine()


def run_turn(query: str, *, gamma: dict[str, Any] | None = None, **_ignored):
    """Run one turn through the local NRE engine. Returns a `TurnResult`.

    Extra kwargs are accepted but ignored for backwards-compat with earlier
    drafts that passed `scratchpad_carry`.
    """
    return _run_turn(query, gamma=gamma)
