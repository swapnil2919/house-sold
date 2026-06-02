"""Project-local Neurosymbolic Reasoning Engine for property queries.

Pipeline:
    PARSE → PLAN → EXECUTE → SYNTHESIZE

`PARSE` and `SYNTHESIZE` use an LLM (neural). `PLAN` and `EXECUTE` are pure
symbolic rules over a tool dependency graph. The whole thing is small and
hackable — edit `plan.py` to teach the agent new intents.
"""

from house_agent.nre.engine import NREEngine, run_turn
from house_agent.nre.schema import Plan, Slots, Trace, TurnResult

__all__ = ["NREEngine", "run_turn", "Plan", "Slots", "Trace", "TurnResult"]
