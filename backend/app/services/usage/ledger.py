"""Cost recording. A call's cost is added to the memo it served (memos.cost_usd / cost_breakdown).
Calls with no memo (Ask, WhatsApp) are only logged. Recording must never break the call it measures."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.config import settings
from app.services.usage.pricing import stt_cost_usd
from app.services.usage.scope import current_scope

logger = logging.getLogger(__name__)

_pending: set[asyncio.Task] = set()


@dataclass
class UsageEvent:
    purpose: str
    memo_id: Optional[str] = None
    user_id: Optional[str] = None
    capture_id: Optional[str] = None
    cost_usd: Optional[float] = None  # None = unpriced, never a guess
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    audio_seconds: Optional[float] = None


def _write(event: UsageEvent) -> None:
    from app.deps import get_supabase

    memo_id = event.memo_id
    if not memo_id and event.capture_id and event.user_id:
        memo_id = memo_id_for_capture(event.user_id, event.capture_id)
    if not memo_id:
        _log_unattached(event)
        return
    try:
        get_supabase().rpc(
            "add_memo_cost",
            {
                "p_memo": memo_id,
                "p_purpose": event.purpose,
                "p_usd": event.cost_usd,
                "p_prompt_tokens": event.prompt_tokens,
                "p_completion_tokens": event.completion_tokens,
                "p_audio_seconds": event.audio_seconds,
            },
        ).execute()
    except Exception:
        logger.warning("memo cost not recorded (memo %s, %s)", memo_id, event.purpose, exc_info=True)


def _log_unattached(event: UsageEvent) -> None:
    logger.info("usage without memo: %s cost_usd=%s user=%s", event.purpose, event.cost_usd, event.user_id)


def memo_id_for_capture(user_id: str, capture_id: str) -> Optional[str]:
    """A desktop capture reserves its memo row up front, so live STT can find it by capture id."""
    from app.deps import get_supabase

    try:
        rows = (
            get_supabase()
            .table("memos")
            .select("id")
            .eq("user_id", user_id)
            .eq("client_capture_id", capture_id)
            .limit(1)
            .execute()
            .data
        )
        return str(rows[0]["id"]) if rows else None
    except Exception:
        logger.warning("memo lookup for capture %s failed", capture_id, exc_info=True)
        return None


def record_usage(event: UsageEvent) -> None:
    """Fire and forget. Safe from sync code, async code and a finally block."""
    if not settings.USAGE_LEDGER_ENABLED:
        return
    scope = current_scope()
    event.memo_id = event.memo_id or scope.memo_id
    event.user_id = event.user_id or scope.user_id
    event.capture_id = event.capture_id or scope.capture_id
    if not (event.memo_id or event.capture_id):
        _log_unattached(event)
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _write(event)
        return
    task = loop.create_task(asyncio.to_thread(_write, event))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


def record_llm_usage(provider: str, call_meta: dict[str, Any]) -> None:
    """`call_meta` is the provider's last_call_meta: tokens, and cost when the vendor reports it."""
    record_usage(
        UsageEvent(
            purpose=current_scope().purpose,
            cost_usd=call_meta.get("cost_usd"),
            prompt_tokens=call_meta.get("prompt_tokens"),
            completion_tokens=call_meta.get("completion_tokens"),
        )
    )


def record_stt_usage(
    provider: str,
    mode: str,
    audio_seconds: float,
    *,
    channels: int = 1,
    tier: str = "",
    purpose: Optional[str] = None,
    memo_id: Optional[str] = None,
) -> None:
    record_usage(
        UsageEvent(
            purpose=purpose or current_scope().purpose,
            memo_id=memo_id,
            cost_usd=stt_cost_usd(provider, mode, audio_seconds, channels, tier=tier),
            audio_seconds=round(audio_seconds, 2),
        )
    )


async def flush() -> None:
    """Wait for queued writes. Tests and graceful shutdown use it; requests never wait."""
    if _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)
