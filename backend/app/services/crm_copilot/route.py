"""Route WhatsApp FSM vs CRM copilot without a new conversation state."""

from __future__ import annotations

import re
from typing import Any, Optional

_RESET_RE = re.compile(
    r"^(?:/?reset|nueva conversaci[oó]n|nueva sesi[oó]n|olvida(?:\s+esto|\s+todo)?|"
    r"empezar de cero|empieza de cero|start over|clear session)$",
    re.I,
)
_SWITCH_RE = re.compile(
    r"(?:^|\b)(?:otro|otra)\s+(?:deal|negocio|contacto|empresa)\b|"
    r"\bcambia(?:r)?\s+(?:de\s+)?(?:deal|contacto|tema)\b|"
    r"\bahora\s+(?:hablemos|habla)\s+de\b|"
    r"\b(?:new|switch)\s+(?:deal|contact)\b",
    re.I,
)


def is_reset_command(text: str) -> bool:
    return bool(_RESET_RE.match((text or "").strip()))


def is_focus_switch(text: str) -> bool:
    return bool(_SWITCH_RE.search((text or "").strip()))


def should_handle_with_copilot(state: Optional[Any]) -> bool:
    if state is None:
        return True
    status = getattr(state, "state", None) or "idle"
    artifacts = getattr(state, "pending_artifact_ids", None) or {}
    copilot = artifacts.get("copilot") or {}
    if copilot:
        return True
    return status in ("idle", None)
