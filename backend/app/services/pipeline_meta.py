"""Per-memo pipeline timings and LLM prompt snapshots.

Stored on memos.pipeline_meta. Stages append across STT then extract so a
HubSpot recording keeps both halves. Re-extract appends another extract run.

Prompt bodies stay in-memory for logging; persisted JSON keeps char counts
and model/token metadata so the row cannot blow past JSONB limits.
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
_EXTRACTION_SOURCE_TYPES = frozenset(
    {"voice_memo", "meeting_transcript", "hubspot_call"}
)


def extraction_source_type(raw: Optional[str]) -> str:
    value = (raw or "").strip()
    if value in _EXTRACTION_SOURCE_TYPES:
        return value
    return "voice_memo"


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


def slim_stage_for_storage(stage: dict) -> dict[str, Any]:
    """Drop prompt bodies; keep timings, model, tokens, and char counts."""
    src = dict(stage or {})
    prompts = src.pop("prompts", None)
    out: dict[str, Any] = {k: v for k, v in src.items() if v is not None}
    if not isinstance(prompts, list):
        return out
    slim_prompts: list[dict[str, Any]] = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        rec: dict[str, Any] = {}
        role = prompt.get("role")
        if role:
            rec["role"] = role
        chars = prompt.get("chars")
        if chars is None and isinstance(prompt.get("content"), str):
            chars = len(prompt["content"])
        if chars is not None:
            rec["chars"] = chars
        slim_prompts.append(rec)
    if slim_prompts:
        out["prompts"] = slim_prompts
    return out


def slim_stages_for_storage(stages: Optional[list]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for stage in stages or []:
        if isinstance(stage, dict):
            out.append(slim_stage_for_storage(stage))
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
    buf: list = []
    token = _STAGES.set(buf)
    try:
        yield buf
    finally:
        _STAGES.reset(token)


def _timings_only(stages: list[dict]) -> list[dict[str, Any]]:
    keys = ("name", "ms", "at", "model", "provider", "error")
    out: list[dict[str, Any]] = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        rec = {k: stage[k] for k in keys if k in stage and stage[k] is not None}
        if rec:
            out.append(rec)
    return out


def persist_pipeline_meta(
    supabase: Any,
    memo_id: str,
    stages: Optional[list] = None,
) -> None:
    buf = stages if stages is not None else (_STAGES.get() or [])
    if not memo_id:
        return
    slimed = slim_stages_for_storage(list(buf))
    try:
        row = (
            supabase.table("memos")
            .select("pipeline_meta")
            .eq("id", memo_id)
            .limit(1)
            .execute()
        )
        existing = ((row.data or [{}])[0] or {}).get("pipeline_meta")
        extra: dict[str, Any] = {
            "persisted_at": datetime.now(timezone.utc).isoformat(),
        }
        meta = merge_pipeline_meta(existing, slimed, **extra)
        if meta.get("stages"):
            meta.pop("empty_run", None)
        else:
            meta["empty_run"] = True
        supabase.table("memos").update({"pipeline_meta": meta}).eq("id", memo_id).execute()
    except Exception as e:
        logger.warning("Could not persist pipeline_meta for memo %s: %s", memo_id, e)
        try:
            row = (
                supabase.table("memos")
                .select("pipeline_meta")
                .eq("id", memo_id)
                .limit(1)
                .execute()
            )
            existing = ((row.data or [{}])[0] or {}).get("pipeline_meta")
            meta = merge_pipeline_meta(
                existing,
                _timings_only(slimed),
                persist_error=str(e)[:300],
                persisted_at=datetime.now(timezone.utc).isoformat(),
            )
            supabase.table("memos").update({"pipeline_meta": meta}).eq("id", memo_id).execute()
        except Exception as e2:
            logger.warning(
                "Could not persist slim pipeline_meta for memo %s: %s", memo_id, e2
            )
