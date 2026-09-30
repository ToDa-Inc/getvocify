"""Append-only cost ledger (usage_events). Recording must never break the call it measures."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.services.usage.pricing import stt_cost_usd
from app.services.usage.scope import current_scope

logger = logging.getLogger(__name__)

_pending: set[asyncio.Task] = set()


@dataclass
class UsageEvent:
    kind: str  # "llm" | "stt"
    provider: str
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None
    audio_seconds: Optional[float] = None
    channels: Optional[int] = None
    cost_usd: Optional[float] = None
    cost_source: str = "unpriced"
    duration_ms: Optional[int] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def row(self) -> dict[str, Any]:
        scope = current_scope()
        out: dict[str, Any] = {
            "kind": self.kind,
            "provider": self.provider,
            "model": self.model,
            "purpose": scope.purpose,
            "user_id": scope.user_id,
            "company_id": scope.company_id,
            "memo_id": scope.memo_id,
            "capture_id": scope.capture_id,
            "scope_id": scope.scope_id,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cached_tokens": self.cached_tokens,
            "audio_seconds": self.audio_seconds,
            "channels": self.channels,
            "cost_usd": self.cost_usd,
            "cost_source": self.cost_source,
            "duration_ms": self.duration_ms,
            "meta": self.meta,
        }
        return {k: v for k, v in out.items() if v is not None}


def _insert(row: dict[str, Any]) -> None:
    from app.deps import get_supabase

    try:
        get_supabase().table("usage_events").insert(row).execute()
    except Exception:
        logger.warning("usage ledger insert failed", exc_info=True)


def record_usage(event: UsageEvent) -> None:
    """Fire and forget. Safe from sync code, async code and a finally block."""
    if not settings.USAGE_LEDGER_ENABLED:
        return
    row = event.row()  # read the scope now: a background task would run outside it
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _insert(row)
        return
    task = loop.create_task(asyncio.to_thread(_insert, row))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


def record_llm_usage(provider: str, call_meta: dict[str, Any], *, duration_ms: Optional[int] = None) -> None:
    """`call_meta` is the provider's last_call_meta: model, token counts, and cost when reported."""
    cost = call_meta.get("cost_usd")
    record_usage(
        UsageEvent(
            kind="llm",
            provider=provider,
            model=call_meta.get("model"),
            prompt_tokens=call_meta.get("prompt_tokens"),
            completion_tokens=call_meta.get("completion_tokens"),
            reasoning_tokens=call_meta.get("reasoning_tokens"),
            cached_tokens=call_meta.get("cached_tokens"),
            cost_usd=cost,
            cost_source="provider_reported" if cost is not None else "unpriced",
            duration_ms=duration_ms,
        )
    )


def record_stt_usage(
    provider: str,
    mode: str,
    audio_seconds: float,
    *,
    channels: int = 1,
    model: Optional[str] = None,
    duration_ms: Optional[int] = None,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    cost = stt_cost_usd(provider, mode, audio_seconds, channels, tier=model or "")
    record_usage(
        UsageEvent(
            kind="stt",
            provider=provider,
            model=model,
            audio_seconds=round(audio_seconds, 2),
            channels=channels,
            cost_usd=cost,
            cost_source="computed" if cost is not None else "unpriced",
            duration_ms=duration_ms,
            meta={"mode": mode, **(meta or {})},
        )
    )


async def flush() -> None:
    """Wait for queued inserts. Tests and graceful shutdown use it; requests never wait."""
    if _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)
