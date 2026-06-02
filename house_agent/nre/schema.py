"""Pydantic schemas shared across the NRE pipeline stages."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Intent = Literal["search", "rate", "compare", "advice", "smalltalk"]


class Slots(BaseModel):
    """Structured representation of a parsed user query."""

    intent: Intent = "search"
    city: str | None = None
    locality: str | None = None
    bhk: int | None = None
    min_price_inr: int | None = None
    max_price_inr: int | None = None
    property_type: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    def has_minimum_for(self, intent: Intent) -> bool:
        if intent in {"search", "rate", "compare", "advice"}:
            return bool(self.city)
        return True


class PlanStep(BaseModel):
    tool: str
    args: dict[str, Any]
    rationale: str = ""


class Plan(BaseModel):
    intent: Intent
    steps: list[PlanStep]
    notes: list[str] = Field(default_factory=list)


class TraceEntry(BaseModel):
    stage: Literal["parse", "plan", "execute", "synthesize"]
    detail: dict[str, Any]


class Trace(BaseModel):
    entries: list[TraceEntry] = Field(default_factory=list)

    def add(self, stage: str, **detail: Any) -> None:
        self.entries.append(TraceEntry(stage=stage, detail=detail))  # type: ignore[arg-type]


class TurnResult(BaseModel):
    answer: str
    slots: Slots
    plan: Plan
    tool_outputs: dict[str, Any] = Field(default_factory=dict)
    listings: list[dict[str, Any]] = Field(default_factory=list)
    price_summary: dict[str, Any] | None = None
    locality_breakdown: list[dict[str, Any]] | None = None
    trace: Trace = Field(default_factory=Trace)
    error: str | None = None
