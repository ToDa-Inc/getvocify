"""Per-memo pipeline timings and LLM prompt snapshots.

Stored on memos.pipeline_meta. Stages append across STT then extract so a
HubSpot recording keeps both halves. Re-extract appends another extract run.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

_STAGES: ContextVar[Optional[list]] = ContextVar("pipeline_stages", default=None)

PROMPT_CHAR_CAP = 80_000


def snapshot_prompts(
    messages: list[dict],
    *,
    max_chars: int = PROMPT_CHAR_CAP,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages or []:
        content = msg.get("content")
        if content is None:
            content = ""
        elif not isinstance(content, str):
            content = str(content)
        rec: dict[str, Any] = {
            "role": msg.get("role") or "user",
            "chars": len(content),
        }
        if len(content) > max_chars:
            rec["content"] = (
                content[:max_chars]
                + f"\n…[truncated {len(content) - max_chars} chars]"
            )
        else:
            rec["content"] = content
        out.append(rec)
    return out


def record_stage(name: str, started: float, **info: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "name": name,
        "ms": max(0, int(round((time.perf_counter() - started) * 1000))),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    for key, value in info.items():
        if value is not None:
            rec[key] = value
    buf = _STAGES.get()
    if buf is not None:
        buf.append(rec)
    return rec


def merge_pipeline_meta(
    existing: Optional[dict],
    stages: list[dict],
    **fields: Any,
) -> dict[str, Any]:
    meta = dict(existing or {})
    merged = list(meta.get("stages") or [])
    merged.extend(stages or [])
    meta["stages"] = merged
    meta["total_ms"] = sum(
        int(s.get("ms") or 0) for s in merged if isinstance(s, dict)
    )
    for key, value in fields.items():
        if value is not None:
            meta[key] = value
    return meta


@contextmanager
def pipeline_run() -> Iterator[list]:
    token = _STAGES.set([])
    try:
        yield _STAGES.get() or []
    finally:
        _STAGES.reset(token)


def persist_pipeline_meta(
    supabase: Any,
    memo_id: str,
    stages: Optional[list] = None,
) -> None:
    buf = stages if stages is not None else (_STAGES.get() or [])
    if not memo_id or not buf:
        return
    try:
        row = (
            supabase.table("memos")
            .select("pipeline_meta")
            .eq("id", memo_id)
            .limit(1)
            .execute()
        )
        existing = ((row.data or [{}])[0] or {}).get("pipeline_meta")
        meta = merge_pipeline_meta(existing, list(buf))
        supabase.table("memos").update({"pipeline_meta": meta}).eq("id", memo_id).execute()
    except Exception as e:
        logger.warning("Could not persist pipeline_meta for memo %s: %s", memo_id, e)
