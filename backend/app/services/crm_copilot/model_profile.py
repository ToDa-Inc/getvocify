"""Per-model request parameters for the Ask loop.

`request_extra` is the only place that knows how a model family wants to be called.
"""

from __future__ import annotations

from typing import Optional

from app.config import settings

_DEEPSEEK = ("deepseek/",)
# Answers are short. Without a cap OpenRouter reserves the model's whole output window (65k tokens) up front and
# refuses the call when the balance cannot cover that, even though a real answer costs a fraction of a cent.
MAX_OUTPUT_TOKENS = 4096
HIGH_EFFORT_OUTPUT_TOKENS = 8192  # reasoning tokens count against the cap


def request_extra(model: Optional[str], effort: str = "low") -> Optional[dict]:
    """Per-call request parameters. `effort` comes from effort.choose_effort: low for lookups, high for analysis.

    DeepSeek V4.1 Flash reasons at the given effort (measured on the Ask eval: at low it is as accurate as reasoning
    off and ~50% slower; default effort was less accurate and over-explored). Its reasoning is replayed between tool
    rounds by the loop. OpenRouter routes this model across hosts: only hosts that honour tools and reasoning and do
    not keep the prompts (transcript quotes travel in tool results)."""
    effort = "high" if effort == "high" else "low"
    extra: dict = {"reasoning": {"effort": effort}, "max_tokens": HIGH_EFFORT_OUTPUT_TOKENS if effort == "high" else MAX_OUTPUT_TOKENS}
    if (model or "").strip().lower().startswith(_DEEPSEEK):
        extra["provider"] = {"require_parameters": True, "data_collection": "deny"}
    return extra


def ask_model() -> str:
    """Web Ask model. An empty ASK_MODEL falls back to the shared CRM copilot model."""
    return (settings.ASK_MODEL or "").strip() or settings.CRM_COPILOT_MODEL


def ask_fallback_model() -> Optional[str]:
    value = (settings.ASK_FALLBACK_MODEL or "").strip()
    return value or None
