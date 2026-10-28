"""A replayed call reads what it would have read on its own day: that day's date and the playbook version the call was
pinned to. Company knowledge has no versions and is read as it is now; contact history is not loaded (the replays have
no contact), so nothing learnt after the call can reach it through either.

    python -m evals.strategic.run_current --production-provider --no-judge --only 816ba4f7 --json a.json
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
from datetime import datetime
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=64)
def call_started(memo_id: str | None) -> datetime | None:
    if not memo_id:
        return None
    import os

    from supabase import create_client

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    rows = sb.table("memos").select("created_at").eq("id", memo_id).limit(1).execute().data or []
    return datetime.fromisoformat(rows[0]["created_at"].replace("Z", "+00:00")) if rows else None


def as_of_call(ctx: Any, call: dict, sb: Any, company_id: str) -> Any:
    """`ctx` (a BrainContext read today) with the call's own date and pinned playbook version, when they are known."""
    from app.services.copilot.load_grounding import whole_playbook
    from app.services.copilot.prompts import today_line
    from app.services.playbooks.live import pinned_snapshot

    changes: dict = {}
    started = call_started(call.get("memo_id"))
    if started:
        zone = re.search(r"\(([^)]+)\)\s*$", ctx.today or "")
        changes["today"] = today_line(zone.group(1) if zone else None, now=started)
    version = call.get("playbook_version_id")
    if version and call.get("motion"):
        snapshot = pinned_snapshot(sb, company_id, call["motion"], version)
        if snapshot:
            changes["snapshot"] = whole_playbook(sb, company_id, snapshot)
            changes["playbook_version_id"] = snapshot["version_id"]
    return dataclasses.replace(ctx, **changes) if changes else ctx


def reliable_reads() -> None:
    """A context read once per replayed call must not fall back to empty on one failed read (the live cache does, and in
    production the next reading reads again): retry the read a few times first (eval only: patches this process)."""
    from app.services.copilot import live_context

    original = live_context.cached
    if getattr(original, "_retrying", False):
        return

    async def cached(key, loader, *, fallback=None):
        for attempt in range(4):
            loaded = await original(key, loader, fallback=fallback)
            if not loaded.failed:
                return loaded
            await asyncio.sleep(1 + attempt)
        raise RuntimeError(f"could not read {key[0] if isinstance(key, tuple) else key} after 4 attempts")

    cached._retrying = True
    live_context.cached = cached


def install(api: Any, calls: list[dict]) -> None:
    """Make the live endpoints read each replayed call as of its own day (eval only: patches the module in this process)."""
    by_id = {c["id"]: c for c in calls}
    original = api._brain_context
    if getattr(original, "_as_of_call", False):
        return

    async def brain_context(supabase, membership, body):
        ctx = await original(supabase, membership, body)
        call = by_id.get(body.call_id)
        return as_of_call(ctx, call, supabase, membership.company_id) if call else ctx

    brain_context._as_of_call = True
    api._brain_context = brain_context
