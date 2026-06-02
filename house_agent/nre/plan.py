"""PLAN stage: pure symbolic rules. Slots → ordered tool plan.

This is the symbolic core. No LLM here — given parsed slots, the intent
deterministically maps to a tool DAG. Edit this file to teach the agent new
intents or change tool ordering.
"""

from __future__ import annotations

from house_agent.nre.schema import Plan, PlanStep, Slots


def plan_for(slots: Slots) -> Plan:
    """Compile slots into an ordered tool plan."""
    intent = slots.intent

    if intent == "smalltalk":
        return Plan(intent=intent, steps=[], notes=["No tool calls — friendly reply."])

    if not slots.has_minimum_for(intent):
        return Plan(
            intent=intent,
            steps=[],
            notes=["Missing required slot: city. Ask the user before tool calls."],
        )

    if intent == "rate":
        return Plan(
            intent=intent,
            steps=[
                PlanStep(
                    tool="get_price_per_sqft",
                    args={"city": slots.city, "locality": slots.locality},
                    rationale="User asked for per-sqft rate — aggregate listings.",
                ),
            ],
        )

    if intent == "compare":
        return Plan(
            intent=intent,
            steps=[
                PlanStep(
                    tool="get_locality_info",
                    args={"city": slots.city},
                    rationale="Compare localities → fetch breakdown for the city.",
                ),
            ],
        )

    # "search" and "advice" share the same first step.
    steps: list[PlanStep] = [
        PlanStep(
            tool="search_listings",
            args={
                "city": slots.city,
                "locality": slots.locality,
                "bhk": slots.bhk,
                "min_price": slots.min_price_inr,
                "max_price": slots.max_price_inr,
                "property_type": slots.property_type,
                "limit": 30,
            },
            rationale="Primary listings lookup with user filters.",
        ),
    ]
    if intent == "advice" or slots.locality:
        steps.append(
            PlanStep(
                tool="get_price_per_sqft",
                args={"city": slots.city, "locality": slots.locality},
                rationale="Context: report the area's typical per-sqft rate.",
            )
        )
    if intent == "advice":
        steps.append(
            PlanStep(
                tool="get_locality_info",
                args={"city": slots.city},
                rationale="Advice mode: compare against other localities in the city.",
            )
        )
    return Plan(intent=intent, steps=steps)
