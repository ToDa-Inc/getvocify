"""Run a company's stored conversations through today's pipeline again, from the backend
that is asked (the admin console of that environment).

Used to test the whole flow on real history: memos copied into a test company keep only
what was captured (transcript, source, contact, deal, date) and come in with no
extraction. Each one is pinned to the company's playbook like a new capture, then
re-extracted as its author (their role's CRM fields, score, meeting proposal, patterns,
follow-up, intelligence queue) - the same code path as POST /memos/{id}/re-extract.

One run per company per process, one memo at a time: it is a batch, not a live capture.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
_COLUMNS = "*"

_RUNS: dict[str, dict] = {}
_TASKS: set[asyncio.Task] = set()


def reprocessable(rows: list[dict], *, only_unprocessed: bool) -> list[dict]:
    """Memos with a transcript that are not approved (an approved memo already wrote to
    the CRM and re-extract refuses it). only_unprocessed keeps the ones with no extraction."""
    out = []
    for row in rows:
        if not str(row.get("transcript") or "").strip():
            continue
        if row.get("status") == "approved":
            continue
        if only_unprocessed and row.get("extraction"):
            continue
        out.append(row)
    return out


def _load(supabase: Any, company_id: str, limit: int) -> list[dict]:
    return (
        supabase.table("memos")
        .select(_COLUMNS)
        .eq("company_id", company_id)
        .order("created_at", desc=True)
        .limit(limit * 3)
        .execute()
        .data
        or []
    )


def _pin(supabase: Any, memo: dict) -> dict:
    """Pin today's playbook on a memo that has none, as a new capture would. Never raises."""
    from app.services.captures import pin_playbook_on_row

    try:
        pinned = pin_playbook_on_row(supabase, dict(memo))
    except Exception:
        logger.warning("reprocess: playbook pin failed for %s", memo.get("id"), exc_info=True)
        return memo
    changes = {key: value for key, value in pinned.items() if memo.get(key) != value}
    if changes:
        supabase.table("memos").update(changes).eq("id", str(memo["id"])).execute()
    return {**memo, **changes}


async def run_reprocess(supabase: Any, company_id: str, memos: list[dict], *, reextract=None) -> dict:
    if reextract is None:
        from app.api.memos import reextract_memo_row as reextract

    run = _RUNS[company_id]
    for memo in memos:
        try:
            memo = _pin(supabase, memo)
            await reextract(supabase, memo, trigger="reprocess")
            run["done"] += 1
        except Exception as exc:
            run["failed"] += 1
            logger.warning("reprocess: memo %s failed: %s", memo.get("id"), exc)
    run["running"] = False
    run["finished_at"] = datetime.now(timezone.utc).isoformat()
    return run


def progress(company_id: str) -> dict:
    return dict(_RUNS.get(company_id) or {"running": False, "total": 0, "done": 0, "failed": 0})


def start_reprocess(
    supabase: Any,
    company_id: str,
    *,
    limit: int = DEFAULT_LIMIT,
    only_unprocessed: bool = True,
    reextract=None,
) -> dict:
    current = _RUNS.get(company_id)
    if current and current.get("running"):
        return dict(current)
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    memos = reprocessable(_load(supabase, company_id, limit), only_unprocessed=only_unprocessed)[:limit]
    _RUNS[company_id] = {
        "running": bool(memos),
        "total": len(memos),
        "done": 0,
        "failed": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None if memos else datetime.now(timezone.utc).isoformat(),
    }
    if memos:
        task = asyncio.get_event_loop().create_task(run_reprocess(supabase, company_id, memos, reextract=reextract))
        _TASKS.add(task)
        task.add_done_callback(_TASKS.discard)
    return dict(_RUNS[company_id])
