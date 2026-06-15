"""Anthropic client wrapper for PF Coach.

Centralizes model selection and the two call shapes the app needs:

  - ``generate_json`` — structured generation (program weeks, intake placement, nutrition).
    Uses **structured outputs** (``output_config.format`` with a JSON schema) so the model
    returns schema-valid JSON directly — no brittle ```json fence-stripping like MARLON did.
  - ``chat`` — free-form conversational turn (the intake interview).

Defaults to ``claude-opus-4-8`` with **adaptive thinking** for the reasoning-heavy
generations; ``claude-haiku-4-5`` is available for cheap/simple calls. Model IDs and the
request surface follow the current Anthropic API (adaptive thinking only — no
``budget_tokens``; no ``temperature``/``top_p`` on Opus 4.8).
"""

import json
from typing import Any, Dict, List, Optional

import anthropic

from config import settings

# Model IDs (current as of the Anthropic model catalog).
OPUS = "claude-opus-4-8"      # most capable — program generation, intake reasoning
SONNET = "claude-sonnet-4-6"  # balanced — conversational interview
HAIKU = "claude-haiku-4-5"    # fast/cheap — simple generation (e.g. extra recipes)

_client: Optional[anthropic.Anthropic] = None


def client() -> anthropic.Anthropic:
    """Lazily-constructed singleton. Raises a clear error if the key is unset."""
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def is_configured() -> bool:
    return bool(settings.anthropic_api_key)


def _first_text(response) -> str:
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


def _loads_lenient(text: str) -> Any:
    """Parse JSON, tolerating an accidental ```json fence (structured outputs shouldn't
    produce one, but this keeps us robust)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
        t = t.strip()
    return json.loads(t)


def generate_json(
    *,
    system: str,
    user: str,
    schema: Dict[str, Any],
    model: str = OPUS,
    max_tokens: int = 8000,
    thinking: bool = True,
    effort: str = "high",
) -> Any:
    """Structured generation. Returns parsed JSON matching ``schema``."""
    output_config: Dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
    kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": output_config,
    }
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
        output_config["effort"] = effort

    response = client().messages.create(**kwargs)
    return _loads_lenient(_first_text(response))


def chat(
    *,
    system: str,
    messages: List[Dict[str, str]],
    model: str = SONNET,
    max_tokens: int = 1024,
) -> str:
    """Free-form conversational turn. Returns the assistant's text."""
    response = client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return _first_text(response)
