"""C04 facts from one transcript: interest, objections, commitments. One model call per revision."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.intelligence.worker import revision_for_memo

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "intelligence_v1.md"
PROMPT_VERSION = "intelligence_v1"

_INTEREST = frozenset({"high", "medium", "low", "none"})
_CATEGORY = frozenset({"price", "timing", "authority", "competitor", "status_quo", "trust", "other"})
_RESOLUTION = frozenset({"resolved", "open", "unknown"})
_KIND = frozenset({"call", "email", "send", "meeting", "other"})
_ORIGIN = frozenset({"rep_promise", "prospect_request"})
_TEXT_MAX = 80


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


def shape_intelligence(memo: dict, raw: dict) -> dict:
    """Keep what the transcript backs. A quote that is not in the text removes its fact."""
    memo_id = str(memo.get("id") or "")
    transcript = str(memo.get("transcript") or "")
    evidence: dict[str, dict] = {}

    interest = raw.get("interest")
    pain = raw.get("pain_confirmed")

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
        due = _due(item.get("due_at"))
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
            "temporal_precision": "time",
            "evidence_refs": [ref["id"]],
        })

    backed = bool(objections or commitments or interest in _INTEREST)
    return {
        "version": 1,
        "input_revision": revision_for_memo(memo),
        "status": "ready" if backed else "partial",
        "interest": interest if interest in _INTEREST else None,
        "pain_confirmed": pain if isinstance(pain, bool) else None,
        "objections": objections,
        "commitments": commitments,
        "meeting": {"agreed": None, "starts_at": None, "timezone": None, "precision": "unknown", "evidence_refs": []},
        "competitor_mentions": [],
        "playbook_observations": [],
        "evidence": list(evidence.values()),
        "prompt_version": PROMPT_VERSION,
    }


def build_messages(memo: dict) -> list[dict]:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    payload = {
        "captured_at": str(memo.get("capture_started_at") or memo.get("created_at") or ""),
        "timezone": str(memo.get("timezone") or "Europe/Madrid"),
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

    supabase.table("memos").update(
        {"extraction": extraction_with_intelligence(memo.get("extraction"), shaped)}
    ).eq("id", str(memo_id)).execute()
    return {"status": "stored", "meta": meta, "intelligence": shaped}


_tasks: set = set()


def schedule_intelligence(supabase: Any, memo_id: str) -> bool:
    """After an extraction save. Off by flag; never blocks the save."""
    if not settings.INTELLIGENCE_EXTRACT_ENABLED:
        return False
    import asyncio
    import logging

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False

    async def run():
        try:
            await ensure_intelligence(supabase, str(memo_id))
        except Exception:
            logging.getLogger(__name__).exception("intelligence extraction failed", extra={"memo_id": str(memo_id)})

    task = loop.create_task(run())
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
