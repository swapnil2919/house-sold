"""Tiny OpenRouter client used by the neural stages.

OpenRouter speaks the OpenAI Chat Completions wire format, so we use the
`openai` SDK pointed at OpenRouter's base URL. One narrow function:
`chat_json` — sends messages, asks the model for JSON, returns a parsed dict.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger("house_agent.nre.llm")

_DEFAULT_MODEL = "anthropic/claude-sonnet-4"


def _client():
    try:
        from openai import OpenAI  # noqa: WPS433
    except ImportError as exc:
        raise RuntimeError(
            "openai package missing — `pip install openai` "
            "(it speaks the OpenRouter wire format)."
        ) from exc
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Put it in .env (or .env.example)."
        )
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )


def _model() -> str:
    return os.environ.get("NRE_LLM_MODEL", _DEFAULT_MODEL)


def chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 800,
) -> dict[str, Any]:
    """Send a chat completion that returns JSON. Falls back to {} on parse fail."""
    client = _client()
    resp = client.chat.completions.create(
        model=_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        extra_headers={
            "HTTP-Referer": "https://github.com/house-sold",
            "X-Title": "House-Sold NRE Agent",
        },
    )
    raw = (resp.choices[0].message.content or "{}").strip()
    # Some models wrap JSON in ```json ... ``` despite response_format. Strip it.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON; raw=%r", raw[:400])
        return {}


def chat_text(
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 800,
) -> str:
    """Free-form text completion (used by SYNTHESIZE)."""
    client = _client()
    resp = client.chat.completions.create(
        model=_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_headers={
            "HTTP-Referer": "https://github.com/house-sold",
            "X-Title": "House-Sold NRE Agent",
        },
    )
    return (resp.choices[0].message.content or "").strip()
