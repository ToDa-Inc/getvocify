"""Ask reads over Vocify's own data. Each read is scoped to the viewer and says how complete it is."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from starlette.concurrency import run_in_threadpool

from app.services.crm_copilot.call_actions import call_targets, record_call_targets
from app.services.crm_copilot.viewer import Viewer, resolve_viewer
from app.services.hoy.assigned import fresh_connection
from app.services.hoy.context import (
    build_priority_page,
    is_stale,
    load_context,
    maybe_refresh_assigned_context,
    snapshot_from_rows,
)
from app.services.hoy.memo_facts import apply_memo_facts, load_memo_facts
from app.services.team_insights.aggregate import (
    TeamAccessError,
    authorized_scope,
    load_team_adherence_inputs,
    team_adherence,
)
from app.services.team_insights.objections import objection_counts

VOCIFY_READS = frozenset({"get_team_metrics", "list_conversations", "get_objections", "get_call_priorities"})

_MEMO_COLUMNS = "id,user_id,company_id,created_at,capture_started_at,hubspot_contact_id,hubspot_deal_id,extraction"
_IN_CHUNK = 200


def _forbidden() -> dict:
    return {"ok": False, "error": "forbidden", "coverage": "forbidden"}


def _unavailable(**extra) -> dict:
    return {"ok": True, "coverage": "unavailable", "reason": "read_failed", **extra}


def _bounded(raw: Any, *, default: Optional[int], low: int, high: int) -> Optional[int]:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _iso(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _in_company(row: dict, viewer: Viewer) -> bool:
    company = row.get("company_id")
    return company is None or str(company) == viewer.company_id


def _scoped_user_ids(args: dict, viewer: Viewer) -> tuple[Optional[list[str]], str]:
    """Explicit user_id: yourself, or a teammate if you manage. Otherwise what your role reads."""
    requested = str(args.get("user_id") or "").strip()
    if requested and requested != viewer.user_id:
        if not viewer.is_manager or not viewer.is_member(requested):
            return None, "forbidden"
        return [requested], "user"
    if requested or not viewer.is_manager:
        return [viewer.user_id], "me"
    return viewer.readable_user_ids(), "team"


def team_metrics(args: dict, viewer: Viewer, supabase) -> dict:
    if not viewer.is_manager:
        return _forbidden()
    requested = str(args.get("user_id") or "").strip() or None
    if requested and not viewer.is_member(requested):
        return _forbidden()
    try:
        scope = authorized_scope(
            role=viewer.role,
            requested_user_id=requested,
            instruction=str(args.get("instruction") or ""),
        )
    except TeamAccessError:
        return _forbidden()
    motion = str(args.get("motion") or "").strip() or None
    inputs = load_team_adherence_inputs(supabase, viewer.company_id, user_id=scope.get("user_id"), motion=motion)
    metrics = team_adherence(role=viewer.role, **inputs)
    return {"ok": True, "scope": scope, "metrics": metrics, "source": "team_adherence"}


def _plain_summary(raw: Any, limit: int = 600) -> str:
    lines = []
    for line in str(raw or "").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        lines.append(text.lstrip("-*•").strip())
    return " ".join(lines)[:limit]


def _objection(item: Any) -> Optional[dict]:
    if isinstance(item, str):
        return {"quote": item} if item.strip() else None
    if not isinstance(item, dict):
        return None
    out = {key: item.get(key) for key in ("category", "resolution", "quote") if item.get(key)}
    if not out.get("quote") and item.get("text"):
        out["quote"] = item["text"]
    return out or None


def _commitment(item: Any) -> Optional[dict]:
    if isinstance(item, str):
        return {"text": item} if item.strip() else None
    if not isinstance(item, dict) or not item.get("text"):
        return None
    out = {"text": item["text"]}
    if item.get("due_at"):
        out["due_at"] = item["due_at"]
    return out


def _conversation(row: dict, viewer: Viewer) -> dict:
    extraction = row.get("extraction") if isinstance(row.get("extraction"), dict) else {}
    intel = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
    meeting = intel.get("meeting") if isinstance(intel.get("meeting"), dict) else {}
    objections = [o for o in map(_objection, intel.get("objections") or extraction.get("objections") or []) if o]
    commitments = [c for c in map(_commitment, intel.get("commitments") or []) if c]
    out = {
        "memo_id": str(row.get("id") or ""),
        "created_at": row.get("capture_started_at") or row.get("created_at"),
        "author": viewer.author_name(row.get("user_id")),
        "contact_id": row.get("hubspot_contact_id"),
        "deal_id": row.get("hubspot_deal_id"),
        "contact_name": extraction.get("contactName"),
        "company_name": extraction.get("companyName"),
        "summary": _plain_summary(extraction.get("summary")),
        "objections": objections[:5],
        "commitments": commitments[:5],
        "pain_confirmed": intel.get("pain_confirmed"),
        "meeting": (
            {"agreed": meeting.get("agreed"), "starts_at": meeting.get("starts_at")}
            if meeting.get("agreed") is not None
            else None
        ),
    }
    return {key: value for key, value in out.items() if value is not None and value != [] and value != ""}


def _matches(row: dict, needle: str) -> bool:
    extraction = row.get("extraction") if isinstance(row.get("extraction"), dict) else {}
    haystack = " ".join(
        str(extraction.get(key) or "") for key in ("contactName", "companyName", "summary")
    ).lower()
    return needle in haystack


def list_conversations(args: dict, viewer: Viewer, supabase, *, now: datetime) -> dict:
    user_ids, scope = _scoped_user_ids(args, viewer)
    if user_ids is None:
        return _forbidden()
    limit = _bounded(args.get("limit"), default=5, low=1, high=10)
    days = _bounded(args.get("days"), default=None, low=1, high=365)
    needle = str(args.get("query") or "").strip().lower()
    query = supabase.table("memos").select(_MEMO_COLUMNS).in_("user_id", user_ids)
    if args.get("contact_id"):
        query = query.eq("hubspot_contact_id", str(args["contact_id"]))
    if args.get("deal_id"):
        query = query.eq("hubspot_deal_id", str(args["deal_id"]))
    if days:
        query = query.gte("created_at", _iso(now - timedelta(days=days)))
    fetch = 200 if needle else max(50, limit + 1)
    try:
        rows = list(query.order("created_at", desc=True).limit(fetch).execute().data or [])
    except Exception:
        return _unavailable(scope=scope, items=[])
    rows = [row for row in rows if _in_company(row, viewer)]
    if needle:
        rows = [row for row in rows if _matches(row, needle)]
    return {
        "ok": True,
        "coverage": "complete",
        "scope": scope,
        "items": [_conversation(row, viewer) for row in rows[:limit]],
        "has_more": len(rows) > limit,
    }


def _instant(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _pattern_text(row: dict) -> Optional[str]:
    pattern_id = str(row.get("pattern_id") or "")
    if not pattern_id.startswith("objection:"):
        return None
    return pattern_id[len("objection:"):].strip() or None


def objections(args: dict, viewer: Viewer, supabase, *, now: datetime) -> dict:
    user_ids, scope = _scoped_user_ids(args, viewer)
    if user_ids is None:
        return _forbidden()
    days = _bounded(args.get("days"), default=30, low=1, high=90)
    start = now - timedelta(days=days)
    end = now + timedelta(seconds=1)
    try:
        memos = (
            supabase.table("memos")
            .select("id,user_id,company_id,created_at")
            .in_("user_id", user_ids)
            .gte("created_at", _iso(start))
            .execute()
        )
        memo_ids = [str(row["id"]) for row in memos.data or [] if row.get("id") and _in_company(row, viewer)]
        patterns: list[dict] = []
        for offset in range(0, len(memo_ids), _IN_CHUNK):
            result = (
                supabase.table("interaction_patterns")
                .select("memo_id,pattern_id,category,kind,resolution,superseded,created_at")
                .in_("memo_id", memo_ids[offset:offset + _IN_CHUNK])
                .execute()
            )
            patterns.extend(result.data or [])
    except Exception:
        return _unavailable(scope=scope, period_days=days, categories=[])
    categories = objection_counts(patterns, start=start, end=end)
    examples: dict[str, list[str]] = {}
    for row in patterns:
        if row.get("superseded") or row.get("kind") != "objection":
            continue
        created = _instant(row.get("created_at"))
        if created is None or created < start or created >= end:
            continue
        text = _pattern_text(row)
        name = str(row.get("category") or "").strip().lower()
        bucket = examples.setdefault(name, [])
        if text and text not in bucket and len(bucket) < 3:
            bucket.append(text)
    return {
        "ok": True,
        "coverage": "complete",
        "scope": scope,
        "period_days": days,
        "conversations": len(memo_ids),
        "categories": [{**item, "examples": examples.get(item["name"], [])} for item in categories],
    }


def _fold_members(viewer: Viewer) -> list[dict]:
    return [
        {"user_id": member["user_id"], "email": member.get("email"), "name": member.get("full_name")}
        for member in viewer.members
        if member.get("user_id") and (member.get("status") or "active") == "active"
    ]


async def call_priorities(args: dict, viewer: Viewer, supabase, *, now: datetime) -> dict:
    """The same list as the Hoy screen: only contacts the CRM assigns to the viewer."""
    limit = _bounded(args.get("limit"), default=5, low=1, high=20)
    observed_at = _iso(now)
    try:
        connected, rows, provider, portal_id, connection = load_context(supabase, viewer.company_id)
    except Exception:
        return _unavailable(items=[])
    fetch_hint = None
    if connected and connection is not None and not rows:
        try:
            connection = await fresh_connection(supabase, connection)
            rows, fetch_hint = await run_in_threadpool(
                maybe_refresh_assigned_context,
                supabase,
                viewer.company_id,
                connection,
                rows,
                _fold_members(viewer),
                observed_at=observed_at,
            )
        except Exception:
            fetch_hint = {"connected": True, "coverage": "unavailable", "candidates": [], "observed_at": None}
    if not connected:
        snapshot = {"connected": False, "coverage": "unavailable", "candidates": []}
    elif fetch_hint is not None:
        snapshot = {**fetch_hint, "provider": provider, "portal_id": portal_id}
    else:
        snapshot = {**snapshot_from_rows(rows, connected=True), "provider": provider, "portal_id": portal_id}
        candidates = snapshot.get("candidates") or []
        mine = [str(row["contact_id"]) for row in candidates if row.get("owner_user_id") == viewer.user_id]
        if mine:
            try:
                facts = load_memo_facts(supabase, viewer.company_id, mine, now=now)
                snapshot["candidates"] = apply_memo_facts(candidates, facts)
            except Exception:
                pass
    page = build_priority_page(snapshot=snapshot, user_id=viewer.user_id, role=viewer.role, now=now, limit=limit)
    items = []
    for row in page["items"]:
        item = {
            "contact_id": row.get("contact_id"),
            "contact_name": row.get("contact_name"),
            "deal_id": row.get("deal_id"),
            "reason": row.get("reason"),
            "next_action": row.get("next_action"),
            "scheduled_at": row.get("scheduled_at"),
            "coverage": row.get("coverage"),
        }
        items.append({key: value for key, value in item.items() if value is not None})
    return {
        "ok": True,
        "coverage": page["coverage"],
        "observed_at": page.get("observed_at"),
        "provider": provider,
        "items": items,
        "has_more": bool(page.get("next_cursor")),
        "empty_reason": None if items else page.get("title"),
        "stale": bool(connected and rows and is_stale(rows, observed_at)),
        "_call_targets": call_targets(page["items"], provider=provider, connection=connection),
    }


async def run_vocify_read(name: str, args: dict, ctx: Any) -> dict:
    viewer = resolve_viewer(ctx)
    if viewer is None:
        return _forbidden()
    supabase = getattr(ctx, "supabase", None)
    now = datetime.now(timezone.utc)
    if name == "get_team_metrics":
        return team_metrics(args, viewer, supabase)
    if name == "list_conversations":
        return list_conversations(args, viewer, supabase, now=now)
    if name == "get_objections":
        return objections(args, viewer, supabase, now=now)
    if name == "get_call_priorities":
        result = await call_priorities(args, viewer, supabase, now=now)
        record_call_targets(ctx, result.pop("_call_targets", None))
        return result
    return {"ok": False, "error": f"unknown tool {name}"}
