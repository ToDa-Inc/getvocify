"""C04 facts from one transcript: interest, objections, commitments. One model call per revision."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings
from app.services.intelligence.worker import revision_for_memo

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "intelligence_v2.md"
PROMPT_VERSION = "intelligence_v2"

_INTEREST = frozenset({"high", "medium", "low", "none"})
_CATEGORY = frozenset({"price", "timing", "authority", "competitor", "status_quo", "trust", "other"})
_RESOLUTION = frozenset({"resolved", "open", "unknown"})
_KIND = frozenset({"call", "email", "send", "meeting", "other"})
_ORIGIN = frozenset({"rep_promise", "prospect_request"})
_TEXT_MAX = 80
_DEFAULT_TZ = "Europe/Madrid"


def _evidence(memo_id: str, quote: str, transcript: str) -> dict | None:
    text = " ".join(str(quote or "").split())
    if not text or text not in " ".join(transcript.split()):
        return None
    digest = hashlib.sha256(f"{memo_id}:{text}".encode()).hexdigest()[:16]
    return {"id": f"ev-{digest}", "source_type": "transcript", "source_id": memo_id, "quote": text}


def _due(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.isoformat() if parsed.tzinfo else None


def _meeting_start(value: Any) -> tuple[str | None, str]:
    if isinstance(value, str) and len(value.strip()) == 10:
        try:
            return date.fromisoformat(value.strip()).isoformat(), "date"
        except ValueError:
            return None, "unknown"
    due = _due(value)
    return (due, "time") if due else (None, "unknown")


def _zone(name: Any) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or _DEFAULT_TZ))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(_DEFAULT_TZ)


def _commitment_due(value: Any, tz_name: Any) -> tuple[str | None, str]:
    """A day without a time starts that day in the memo timezone, so Hoy shows it that morning."""
    day, precision = _meeting_start(value)
    if precision != "date":
        return day, precision
    start = datetime.combine(date.fromisoformat(day), time(), tzinfo=_zone(tz_name))
    return start.isoformat(), "date"


def _meeting(memo_id: str, raw: Any, transcript: str, evidence: dict[str, dict]) -> dict:
    empty = {"agreed": None, "starts_at": None, "timezone": None, "precision": "unknown", "evidence_refs": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("agreed"), bool):
        return empty
    ref = _evidence(memo_id, raw.get("quote"), transcript)
    if ref is None:
        return empty
    evidence[ref["id"]] = ref
    starts_at, precision = _meeting_start(raw.get("starts_at")) if raw["agreed"] else (None, "unknown")
    return {**empty, "agreed": raw["agreed"], "starts_at": starts_at, "precision": precision, "evidence_refs": [ref["id"]]}


def shape_intelligence(memo: dict, raw: dict) -> dict:
    """Keep what the transcript backs. A quote that is not in the text removes its fact."""
    memo_id = str(memo.get("id") or "")
    transcript = str(memo.get("transcript") or "")
    evidence: dict[str, dict] = {}

    interest = raw.get("interest")
    pain = raw.get("pain_confirmed")
    pain_ref = _evidence(memo_id, raw.get("pain_quote"), transcript) if isinstance(pain, bool) else None
    if pain_ref is None:
        pain = None
    else:
        evidence[pain_ref["id"]] = pain_ref

    objections = []
    for item in raw.get("objections") or []:
        if not isinstance(item, dict):
            continue
        ref = _evidence(memo_id, item.get("quote"), transcript)
        if ref is None:
            continue
        evidence[ref["id"]] = ref
        category = item.get("category") if item.get("category") in _CATEGORY else "other"
        resolution = item.get("resolution") if item.get("resolution") in _RESOLUTION else "unknown"
        objections.append({
            "id": f"obj-{ref['id'][3:]}",
            "category": category,
            "kind": "objection",
            "resolution": resolution,
            "quote": ref["quote"],
            "evidence_refs": [ref["id"]],
        })

    commitments = []
    for item in raw.get("commitments") or []:
        if not isinstance(item, dict):
            continue
        due, precision = _commitment_due(item.get("due_at"), memo.get("timezone"))
        text = " ".join(str(item.get("text") or "").split()).rstrip(".")
        ref = _evidence(memo_id, item.get("quote"), transcript)
        if not due or not text or ref is None:
            continue
        evidence[ref["id"]] = ref
        commitments.append({
            "id": f"com-{ref['id'][3:]}",
            "kind": item.get("kind") if item.get("kind") in _KIND else "other",
            "origin": item.get("origin") if item.get("origin") in _ORIGIN else "rep_promise",
            "text": text[:_TEXT_MAX].rstrip(),
            "due_at": due,
            "temporal_precision": precision,
            "evidence_refs": [ref["id"]],
        })

    meeting = _meeting(memo_id, raw.get("meeting"), transcript, evidence)
    backed = bool(objections or commitments or interest in _INTEREST)
    return {
        "version": 1,
        "input_revision": revision_for_memo(memo),
        "status": "ready" if backed else "partial",
        "interest": interest if interest in _INTEREST else None,
        "pain_confirmed": pain,
        "objections": objections,
        "commitments": commitments,
        "meeting": meeting,
        "competitor_mentions": [],
        "playbook_observations": [],
        "evidence": list(evidence.values()),
        "prompt_version": PROMPT_VERSION,
    }


def build_messages(memo: dict) -> list[dict]:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    payload = {
        "captured_at": str(memo.get("capture_started_at") or memo.get("created_at") or ""),
        "timezone": str(memo.get("timezone") or _DEFAULT_TZ),
        "summary": str((extraction or {}).get("summary") or ""),
        "transcript": str(memo.get("transcript") or ""),
    }
    return [
        {"role": "system", "content": PROMPT_PATH.read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def is_current(memo: dict) -> bool:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    block = (extraction or {}).get("intelligence")
    return (
        isinstance(block, dict)
        and block.get("prompt_version") == PROMPT_VERSION
        and block.get("input_revision") == revision_for_memo(memo)
    )


async def ensure_intelligence(supabase: Any, memo_id: str, *, llm: Any = None) -> dict:
    """Idempotent per revision. A failure leaves the memo as it was."""
    result = supabase.table("memos").select("*").eq("id", str(memo_id)).limit(1).execute()
    rows = list(getattr(result, "data", None) or [])
    if not rows:
        return {"status": "missing"}
    memo = rows[0]
    if is_current(memo):
        return {"status": "current"}
    if llm is None:
        from app.services.llm import LLMClient

        llm = LLMClient()
    shaped, meta = await extract_intelligence(memo, llm)
    if shaped is None:
        return {"status": "no_transcript"}
    from app.services.intelligence.interpret import extraction_with_intelligence

    stored = extraction_with_intelligence(memo.get("extraction"), shaped)
    supabase.table("memos").update({"extraction": stored}).eq("id", str(memo_id)).execute()
    from app.services.memo_extraction_hooks import refresh_meeting_proposal

    refresh_meeting_proposal(supabase, {**memo, "extraction": stored})
    return {"status": "stored", "meta": meta, "intelligence": shaped}


_tasks: set = set()


def schedule_intelligence(supabase: Any, memo_id: str, company_id: str | None = None) -> bool:
    """After an extraction save. Off by the memo company's flag; never blocks the save."""
    import asyncio
    import logging

    from app.services.feature_flags import is_enabled

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    if not company_id:
        try:
            result = supabase.table("memos").select("company_id").eq("id", str(memo_id)).limit(1).execute()
            rows = list(getattr(result, "data", None) or [])
            company_id = rows[0].get("company_id") if rows else None
        except Exception:
            company_id = None
    if not is_enabled(supabase, company_id, "INTELLIGENCE_EXTRACT_ENABLED"):
        return False

    async def run():
        try:
            await ensure_intelligence(supabase, str(memo_id))
        except Exception:
            logging.getLogger(__name__).exception("intelligence extraction failed", extra={"memo_id": str(memo_id)})

    task = loop.create_task(run(), name=f"intelligence:{memo_id}")  # followup._c04_task waits on it
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


async def extract_intelligence(memo: dict, llm: Any) -> tuple[dict | None, dict]:
    """None when there is nothing to read. Metadata carries model and tokens for cost."""
    if not str(memo.get("transcript") or "").strip():
        return None, {}
    raw = await llm.chat_json(
        build_messages(memo),
        model=settings.INTELLIGENCE_MODEL,
        temperature=0.0,
        timeout=60.0,
    )
    meta = dict(getattr(llm, "last_call_meta", None) or {})
    return shape_intelligence(memo, raw if isinstance(raw, dict) else {}), meta
