"""Client-supplied session context for /copilot/suggest (never invented server-side)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def live_assist_kind_from_call_mode(call_mode: str) -> str:
    """Map API call_mode to live-help kind: meeting vs call (speakerphone/softphone)."""
    mode = (call_mode or "speakerphone").strip().lower()
    return "meeting" if mode == "meeting" else "call"


@dataclass(frozen=True)
class SuggestContext:
    contact_id: Optional[str] = None
    live_assist_kind: str = "call"


def resolve_suggest_context(
    contact_id: Optional[str] = None,
    *,
    call_mode: str = "speakerphone",
) -> SuggestContext:
    normalized = str(contact_id or "").strip() or None
    return SuggestContext(
        contact_id=normalized,
        live_assist_kind=live_assist_kind_from_call_mode(call_mode),
    )
