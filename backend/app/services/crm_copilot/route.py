"""Route WhatsApp FSM vs CRM copilot without a new conversation state."""

from __future__ import annotations

from typing import Any, Optional


def should_handle_with_copilot(state: Optional[Any]) -> bool:
    if state is None:
        return True
    status = getattr(state, "state", None) or "idle"
    artifacts = getattr(state, "pending_artifact_ids", None) or {}
    copilot = artifacts.get("copilot") or {}
    if copilot:
        return True
    return status in ("idle", None)
