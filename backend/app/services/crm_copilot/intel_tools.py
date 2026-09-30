"""Ask intelligence tools: read what Vocify captured and what HubSpot holds, with coverage and evidence.

Every result is an envelope: coverage, counts, items and the quotes that back them. The model
narrates; it does not compute. Scope comes from the actor's role, never from the question.

Each tool answers one kind of question. Descriptions say what it is NOT for, so the model does not
call two tools and then report both.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.services.activity_scope import author_display_name
from app.services.crm_copilot import brain_tools, crm_analytics, crm_query, tool_schema
from app.services.crm_copilot.actor import AskActor, ScopeError, current_actor, visible_user_ids
from app.services.hoy.materialize import day_end, fresh_signals
from app.services.hoy.signals import rank_cards

from app.services.hubspot.exceptions import (  # noqa: E402
    HubSpotAuthError,
    HubSpotError,
    HubSpotRateLimitError,
    HubSpotScopeError,
    HubSpotValidationError,
)

logger = logging.getLogger(__name__)

MAX_PERIOD_DAYS = 180
DEFAULT_PERIOD_DAYS = 30
MEMO_COLUMNS = (
    "id,user_id,company_id,status,extraction,capture_started_at,created_at,"
    "interaction_kind,hubspot_contact_id,hubspot_deal_id,sales_motion_key,screening_outcome"
)
_USABLE = frozenset({"pending_review", "approved"})
_NO_CONVERSATION = frozenset({"voicemail", "no_response"})

FORBIDDEN = {"ok": False, "error": "forbidden", "coverage": "forbidden"}
UNAVAILABLE = {"ok": False, "error": "crm_unavailable", "coverage": "unavailable"}


_fn = tool_schema.fn


_PERIOD = {"type": "integer", "description": "Days back, 1-180. Default 30."}
_USER = {"type": "string", "description": "One team member's user id (managers only)."}
_CRM_PERIOD = {
    "month": {"type": "string", "description": "YYYY-MM."},
    "start_date": {"type": "string", "description": "YYYY-MM-DD, inclusive."},
    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive; needs start_date."},
    "period_days": {"type": "integer", "description": "Last N days."},
}
_FILTER = {
    "type": "object",
    "properties": {
        "property": {"type": "string"},
        "operator": {"type": "string", "enum": sorted(crm_query.OPERATORS)},
        "value": {"type": "string"},
        "values": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["property"],
}

_MEMBER_TOOLS = [
    _fn(
        "deal_story",
        "Everything captured about ONE contact: interest, pains, objections and obstacles (and how each ended), promises, open loops. Needs contact_id: search_contacts first.",
        {"contact_id": {"type": "string"}},
        ["contact_id"],
    ),
    _fn(
        "find_interactions",
        "Captured conversations, newest first, with summary and quotes. Filter by contact, objection category, kind (objection|obstacle) or period. For calls to review or quote; not for counts.",
        {
            "contact_id": {"type": "string"},
            "objection_category": {"type": "string"},
            "kind": {"type": "string", "enum": ["objection", "obstacle"]},
            "period_days": _PERIOD,
            "user_id": _USER,
            "limit": {"type": "integer", "description": "1-10. Default 8."},
        },
    ),
    _fn(
        "objection_breakdown",
        "Counts of objections and, separately, obstacles raised in captured calls, by category, and how many stayed open. Not for call activity.",
        {"period_days": _PERIOD, "user_id": _USER, "by_rep": {"type": "boolean", "description": "Per-rep table (managers only)."}},
    ),
    _fn(
        "competitor_mentions",
        "Competitors prospects named in captured calls: how often and in which conversations.",
        {"period_days": _PERIOD, "user_id": _USER},
    ),
    _fn(
        "meetings_agreed",
        "Meetings agreed in captured calls, and the rate where that could be judged. Only what Vocify captured.",
        {"period_days": _PERIOD, "user_id": _USER},
    ),
    _fn(
        "playbook_lookup",
        "The published playbook: the approved answer per objection category, and the process steps.",
        {
            "category": {"type": "string", "description": "Objection category, e.g. price."},
            "topic": {"type": "string", "description": "Free text instead of a category."},
        },
    ),
    _fn(
        "crm_call_stats",
        "HubSpot call activity for a period: total, connected, no answer, voicemail, busy, connection rate. Outbound by default; no period = last 30 days.",
        {
            **_CRM_PERIOD,
            "direction": {"type": "string", "enum": ["outbound", "inbound", "all"]},
            "by_rep": {"type": "boolean", "description": "Per-rep breakdown (managers only)."},
            "compare_previous": {"type": "boolean", "description": "Add the previous month (or equal window) with the change computed."},
            "user_id": _USER,
        },
    ),
    _fn(
        "crm_lost_reasons",
        "Deals lost in HubSpot in a period: count, top reasons, won, win rate. No period = last 90 days.",
        {**_CRM_PERIOD, "top_n": {"type": "integer", "description": "1-10. Default 5."}, "user_id": _USER},
    ),
    _fn(
        "hubspot_describe",
        "Properties of one HubSpot object type (search= a name), or one property in detail with its real options. Only for custom fields or when unsure a property exists.",
        {
            "object_type": {"type": "string", "enum": sorted(crm_query.OBJECTS)},
            "search": {"type": "string", "description": "Part of a name or label. Without it, only custom properties."},
            "property": {"type": "string", "description": "One property: its type and options."},
        },
        ["object_type"],
    ),
    _fn(
        "hubspot_query",
        "Exact figures from HubSpot for ONE object type: a count, a breakdown by a property, sum/avg/min/max of a number, "
        "per day/week/month/hour/weekday, a share of records matching a condition, the change vs the previous period, or top rows. "
        "Names and options are validated: on an error, use the choices it lists. It cannot join object types and knows nothing "
        "of what was said in calls. No period = all time.",
        {
            "object_type": {"type": "string", "enum": sorted(crm_query.OBJECTS)},
            "filters": {"type": "array", "items": _FILTER, "description": "Up to 6 conditions in all (the period counts 2). Option properties take a label or value. Durations need a unit: 2m, 90s, 1.5h. For before/after a date use LT/GT with an ISO date."},
            **_CRM_PERIOD,
            "date_property": {"type": "string", "description": "Date the period applies to. Default: created date, or activity date for calls, meetings, tasks, notes. closedate for 'closed in'."},
            "group_by": {"type": "string", "description": "One property to break the count down by."},
            "date_bucket": {"type": "string", "enum": ["day", "week", "month", "hour", "weekday"], "description": "Count per day/week/month (needs a period) or per hour/weekday of the most recent records."},
            "aggregate": {"type": "string", "enum": sorted(crm_query.AGGREGATES), "description": "Default count; others need metric_property."},
            "metric_property": {"type": "string", "description": "A number property, e.g. amount, call duration."},
            "share_where": {"type": "array", "items": _FILTER, "description": "Adds how many records match and the percent: connection rate, calls over 2m, win rate. Per group with group_by or date_bucket."},
            "compare_previous": {"type": "boolean", "description": "Same question over the window before the period, change computed. Needs a period, no group_by."},
            "properties": {"type": "array", "items": {"type": "string"}, "description": "List mode: up to 8 properties per row."},
            "sort_by": {"type": "string"},
            "sort_dir": {"type": "string", "enum": ["asc", "desc"]},
            "limit": {"type": "integer", "description": "List mode rows, 1-20. Default 10."},
            "user_id": _USER,
        },
        ["object_type"],
    ),
]

_TEAM_TOOLS = list(brain_tools.TEAM_TOOLS)
_MEMBER_TOOLS = _MEMBER_TOOLS[:1] + list(brain_tools.MEMBER_TOOLS) + _MEMBER_TOOLS[1:]

INTEL_TOOL_NAMES = frozenset(t["function"]["name"] for t in _MEMBER_TOOLS + _TEAM_TOOLS)


def intel_tools_for(actor: AskActor) -> list:
    """A member is never shown a team tool."""
    return list(_MEMBER_TOOLS) + (list(_TEAM_TOOLS) if actor.is_team_reader else [])


# ----- shared helpers -------------------------------------------------------------------------


def _instant(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _memo_at(memo: dict) -> datetime:
    return _instant(memo.get("capture_started_at") or memo.get("created_at")) or datetime.now(timezone.utc)


def _extraction(memo: dict) -> dict:
    return memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}


def _intel(memo: dict) -> dict:
    block = _extraction(memo).get("intelligence")
    return block if isinstance(block, dict) else {}


def _contact_name(memo: dict) -> Optional[str]:
    ex = _extraction(memo)
    name = str(ex.get("contactName") or "").strip()
    company = str(ex.get("companyName") or "").strip()
    if name and company:
        return f"{name} ({company})"
    return name or company or None


def _defaulted(args: dict) -> bool:
    return not args.get("period_days")


def _period(args: dict) -> tuple[int, datetime]:
    try:
        days = int(args.get("period_days") or DEFAULT_PERIOD_DAYS)
    except (TypeError, ValueError):
        days = DEFAULT_PERIOD_DAYS
    days = max(1, min(days, MAX_PERIOD_DAYS))
    return days, datetime.now(timezone.utc) - timedelta(days=days)


def _limit(args: dict, default: int = 8) -> int:
    try:
        return max(1, min(int(args.get("limit") or default), 10))
    except (TypeError, ValueError):
        return default


def _envelope(*, n: int, n_analysed: int, coverage: Optional[str] = None, unit: Optional[str] = None, **body) -> dict:
    return {
        "coverage": coverage or ("complete" if n_analysed >= n else "partial"),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "n": n,
        "n_analysed": n_analysed,
        **({"unit": unit} if unit else {}),
        **body,
    }


def _company(ctx, actor):
    service = getattr(ctx, "company", None)
    if service is not None:
        return service
    from app.services.company import CompanyService

    return CompanyService(ctx.supabase)


def _rep_names(ctx, actor: AskActor) -> dict[str, str]:
    if not actor.is_team_reader:
        return {}
    return {
        str(m["user_id"]): author_display_name(m.get("full_name"), m.get("email"))
        for m in _company(ctx, actor).list_members(actor.company_id)
        if m.get("user_id")
    }


def team_roster(ctx, actor: AskActor) -> dict[str, str]:
    """{user_id: name} for owners and admins, so a name in a question can become a user_id. Empty on any failure."""
    try:
        return _rep_names(ctx, actor)
    except Exception:  # noqa: BLE001 - a missing roster must not stop the answer
        return {}


def _load_memos(ctx, actor: AskActor, user_ids: list[str], *, since=None, contact_id=None, limit=60) -> list[dict]:
    query = (
        ctx.supabase.table("memos")
        .select(MEMO_COLUMNS)
        .in_("user_id", user_ids)
        .or_(f"company_id.eq.{actor.company_id},company_id.is.null")
    )
    if contact_id:
        query = query.eq("hubspot_contact_id", contact_id)
    if since is not None:
        query = query.gte("created_at", since.isoformat())
    rows = query.order("created_at", desc=True).limit(limit).execute().data or []
    return [m for m in rows if m.get("status") in _USABLE and _extraction(m)]


def _first_line(text: str) -> str:
    for raw in str(text or "").splitlines():
        line = raw.strip().lstrip("#").strip().lstrip("-*•").strip()
        if line and not raw.strip().startswith("#"):
            return line[:200]
    return ""


def _episodes(memo: dict) -> list[dict]:
    """Objections and obstacles of one memo. v1 blocks have no kind: they were commercial objections."""
    out = []
    for item in _intel(memo).get("objections") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind") if item.get("kind") in ("objection", "obstacle") else "objection"
        reply = item.get("response")
        # C04 stores the rep's reply as {"text": ...} with response_evidence_refs; older blocks held the string.
        reply_text = str(reply.get("text") or "") if isinstance(reply, dict) else str(reply or "")
        reply_refs = [r for r in (item.get("response_evidence_refs") or []) if r]
        out.append(
            {
                "kind": kind,
                "category": item.get("category") or "other",
                "state": item.get("resolution") or item.get("state") or "unknown",
                "quote": item.get("quote") or "",
                "response": reply_text,
                "evidence_refs": [r for r in (item.get("evidence_refs") or []) if r],
                "response_evidence": item.get("response_evidence") or (reply_refs[0] if reply_refs else None),
            }
        )
    if not out:
        out = [
            {"kind": "objection", "category": "other", "state": "unknown", "quote": str(t)[:160], "response": "", "evidence_refs": [], "response_evidence": None}
            for t in _extraction(memo).get("objections") or []
            if isinstance(t, str) and t.strip()
        ]
    return out


def _evidence_items(memo: dict, wanted: set[str], rep: Optional[str]) -> list[dict]:
    out = []
    for item in _intel(memo).get("evidence") or []:
        if isinstance(item, dict) and item.get("id") in wanted and item.get("quote"):
            out.append(
                {
                    "id": item["id"],
                    "memo_id": str(memo.get("id")),
                    "quote": item["quote"],
                    "speaker": item.get("speaker_role"),
                    "at": _memo_at(memo).isoformat(),
                    **({"rep": rep} if rep else {}),
                }
            )
    return out


def _tally(episodes: list[dict]) -> dict:
    def block(kind: str) -> dict:
        rows = [e for e in episodes if e["kind"] == kind]
        by_cat: dict[str, dict] = {}
        for e in rows:
            cat = by_cat.setdefault(e["category"], {"category": e["category"], "count": 0, "open": 0, "resolved": 0, "unknown": 0})
            cat["count"] += 1
            cat[e["state"] if e["state"] in ("open", "resolved") else "unknown"] += 1
        ordered = sorted(by_cat.values(), key=lambda c: (-c["count"], c["category"]))
        return {
            "total": len(rows),
            "open": sum(c["open"] for c in ordered),
            "resolved": sum(c["resolved"] for c in ordered),
            "unknown": sum(c["unknown"] for c in ordered),
            "by_category": ordered,
        }

    return {"objections": block("objection"), "obstacles": block("obstacle")}


# ----- Vocify-data tools ----------------------------------------------------------------------


def _touch(memo: dict, rep: Optional[str]) -> tuple[dict, set[str]]:
    extraction, intel = _extraction(memo), _intel(memo)
    refs: set[str] = set()
    episodes = []
    for e in _episodes(memo):
        refs.update(e["evidence_refs"])
        if e["response_evidence"]:
            refs.add(e["response_evidence"])
        episodes.append(
            {
                "kind": e["kind"],
                "category": e["category"],
                "state": e["state"],
                "quote": e["quote"],
                "evidence": (e["evidence_refs"] or [None])[0],
                **({"rep_response": e["response"], "response_evidence": e["response_evidence"]} if e["response"] else {}),
            }
        )
    commitments = []
    for item in intel.get("commitments") or []:
        if not isinstance(item, dict):
            continue
        ref = (item.get("evidence_refs") or [None])[0]
        if ref:
            refs.add(ref)
        commitments.append({"text": item.get("text"), "due_at": item.get("due_at"), "origin": item.get("origin"), "evidence": ref})
    touch = {
        "memo_id": str(memo.get("id")),
        "at": _memo_at(memo).isoformat(),
        "kind": memo.get("interaction_kind") or "call",
        "summary": _first_line(extraction.get("summary")),
        "interest": intel.get("interest"),
        "pains": [str(p)[:160] for p in (extraction.get("painPoints") or [])[:3]],
        "objections": [e for e in episodes if e["kind"] == "objection"],
        "obstacles": [e for e in episodes if e["kind"] == "obstacle"],
        "commitments": commitments,
        "next_steps": [str(s)[:160] for s in (extraction.get("nextSteps") or [])[:3]],
    }
    if rep:
        touch["rep"] = rep
    return touch, refs


def _signal_items(signals: list, memos_by_id: dict, reps: dict, limit: int) -> tuple[list[dict], int]:
    cards, folded = rank_cards(signals, now=datetime.now(timezone.utc), limit=limit)
    items = []
    for card in cards:
        memo = memos_by_id.get(card.primary.source_memo_id) or {}
        item = {
            "contact": _contact_name(memo),
            "contact_id": card.primary.contact_id,
            "type": card.primary.type,
            "due_at": card.primary.due_at.isoformat() if card.primary.due_at else None,
            "detail": {k: v for k, v in card.primary.payload.items() if k in {"kind", "text", "category", "days_silent", "origin"}},
            "also": [s.type for s in card.supporting],
            "memo_id": card.primary.source_memo_id,
        }
        rep = reps.get(str(memo.get("user_id")))
        if rep:
            item["rep"] = rep
        items.append(item)
    return items, folded


async def _deal_story(args: dict, ctx, actor: AskActor) -> dict:
    contact_id = str(args.get("contact_id") or "").strip()
    if not contact_id:
        return {"ok": False, "error": "contact_id required"}
    user_ids = visible_user_ids(actor, _company(ctx, actor))
    memos = _load_memos(ctx, actor, user_ids, contact_id=contact_id, limit=12)
    reps = _rep_names(ctx, actor)
    touches, evidence = [], []
    for memo in memos:
        touch, refs = _touch(memo, reps.get(str(memo.get("user_id"))))
        touches.append(touch)
        evidence.extend(_evidence_items(memo, refs, touch.get("rep")))
    now = datetime.now(timezone.utc)
    signals = fresh_signals(memos, now=now, day_end=day_end(now, actor.timezone)) if memos else []
    loops, _ = _signal_items(signals, {str(m["id"]): m for m in memos}, reps, 5)
    analysed = sum(1 for m in memos if _intel(m))
    approved = _approved_answers(ctx, actor, touches)
    evidence.extend({"id": a["evidence"], "quote": a["answer"], "speaker": "playbook", "rep": a["motion"]} for a in approved)
    return _envelope(
        n=len(memos),
        n_analysed=analysed,
        contact_id=contact_id,
        contact=next((n for n in (_contact_name(m) for m in memos) if n), None),
        touches=touches,
        open_loops=loops,
        **({"approved_answers": [{k: v for k, v in a.items() if k != "motion"} for a in approved]} if approved else {}),
        evidence=evidence,
    )


def _approved_answers(ctx, actor: AskActor, touches: list[dict]) -> list[dict]:
    """The company's approved answer for each objection still open on this contact, so preparing a call needs no second lookup."""
    open_categories = {o["category"] for t in touches[:1] for o in t["objections"] if o["state"] in ("open", "unknown")}
    if not open_categories:
        return []
    answers, _ = brain_tools.published_answers(ctx, actor)
    return [{"category": c, **answers[c]} for c in sorted(open_categories) if c in answers]


async def _find_interactions(args: dict, ctx, actor: AskActor) -> dict:
    user_ids = visible_user_ids(actor, _company(ctx, actor), args.get("user_id"))
    days, since = _period(args)
    memos = _load_memos(ctx, actor, user_ids, since=since, contact_id=(args.get("contact_id") or None))
    category = str(args.get("objection_category") or "").strip().lower()
    kind = args.get("kind") if args.get("kind") in ("objection", "obstacle") else None
    if category or kind:
        memos = [
            m for m in memos
            if any((not category or e["category"] == category) and (not kind or e["kind"] == kind) for e in _episodes(m))
        ]
    reps = _rep_names(ctx, actor)
    items, evidence = [], []
    for memo in memos[: _limit(args)]:
        intel = _intel(memo)
        episodes = _episodes(memo)
        matching = [e for e in episodes if (not category or e["category"] == category) and (not kind or e["kind"] == kind)]
        quotes = [
            {"kind": e["kind"], "category": e["category"], "quote": e["quote"], "evidence": (e["evidence_refs"] or [None])[0]}
            for e in matching[:2]
            if e["quote"]
        ]
        item = {
            "memo_id": str(memo.get("id")),
            "at": _memo_at(memo).isoformat(),
            "kind": memo.get("interaction_kind") or "call",
            "contact_id": memo.get("hubspot_contact_id"),
            "contact": _contact_name(memo),
            "summary": _first_line(_extraction(memo).get("summary")),
            "interest": intel.get("interest"),
            "objections": sorted({e["category"] for e in episodes if e["kind"] == "objection"}),
            "obstacles": sorted({e["category"] for e in episodes if e["kind"] == "obstacle"}),
            "quotes": quotes,
        }
        rep = reps.get(str(memo.get("user_id")))
        if rep:
            item["rep"] = rep
        items.append(item)
        evidence.extend(_evidence_items(memo, {q["evidence"] for q in quotes if q["evidence"]}, rep))
    analysed = sum(1 for m in memos if _intel(m))
    return _envelope(n=len(memos), n_analysed=analysed, period_days=days, period_defaulted=_defaulted(args), items=items, evidence=evidence)


async def _objection_breakdown(args: dict, ctx, actor: AskActor) -> dict:
    user_ids = visible_user_ids(actor, _company(ctx, actor), args.get("user_id"))
    days, since = _period(args)
    memos = _load_memos(ctx, actor, user_ids, since=since, limit=300)
    episodes = [e for m in memos for e in _episodes(m)]
    analysed = sum(1 for m in memos if _intel(m))
    body = _tally(episodes)
    if args.get("by_rep"):
        if not actor.is_team_reader:
            raise ScopeError("by_rep is for owners and admins")
        reps = _rep_names(ctx, actor)
        rows = []
        for uid in sorted(reps, key=lambda u: reps[u].casefold()):
            mine = [m for m in memos if str(m.get("user_id")) == uid]
            if mine:
                rows.append({"rep": reps[uid], "conversations": len(mine), **_tally([e for m in mine for e in _episodes(m)])})
        body["by_rep"] = rows
    return _envelope(n=len(memos), n_analysed=analysed, period_days=days, period_defaulted=_defaulted(args), **body)


def _open_obstacles(memos: list[dict], reps: dict) -> list[dict]:
    """Open obstacles on each contact's latest conversation: someone to call back, not an objection."""
    latest: dict[str, dict] = {}
    for memo in memos:  # newest first
        latest.setdefault(str(memo.get("hubspot_contact_id") or memo.get("id")), memo)
    out = []
    for memo in latest.values():
        for e in _episodes(memo):
            if e["kind"] == "obstacle" and e["state"] in ("open", "unknown"):
                item = {"contact": _contact_name(memo), "contact_id": memo.get("hubspot_contact_id"), "category": e["category"], "quote": e["quote"], "memo_id": str(memo.get("id"))}
                rep = reps.get(str(memo.get("user_id")))
                if rep:
                    item["rep"] = rep
                out.append(item)
    return out[:10]


async def _competitor_mentions(args: dict, ctx, actor: AskActor) -> dict:
    user_ids = visible_user_ids(actor, _company(ctx, actor), args.get("user_id"))
    days, since = _period(args)
    memos = _load_memos(ctx, actor, user_ids, since=since, limit=300)
    found: dict[str, dict] = {}
    for memo in memos:
        names = list(_extraction(memo).get("competitors") or [])
        names += [c.get("name") for c in _intel(memo).get("competitor_mentions") or [] if isinstance(c, dict)]
        for raw in {str(n).strip() for n in names if n and str(n).strip()}:
            row = found.setdefault(raw.casefold(), {"competitor": raw, "mentions": 0, "conversations": []})
            row["mentions"] += 1
            if len(row["conversations"]) < 3:
                row["conversations"].append({"memo_id": str(memo["id"]), "contact": _contact_name(memo)})
    items = sorted(found.values(), key=lambda r: (-r["mentions"], r["competitor"].casefold()))
    analysed = sum(1 for m in memos if _intel(m))
    return _envelope(n=len(memos), n_analysed=analysed, period_days=days, period_defaulted=_defaulted(args), items=items)


async def _meetings_agreed(args: dict, ctx, actor: AskActor) -> dict:
    user_ids = visible_user_ids(actor, _company(ctx, actor), args.get("user_id"))
    days, since = _period(args)
    memos = [m for m in _load_memos(ctx, actor, user_ids, since=since, limit=300) if m.get("screening_outcome") not in _NO_CONVERSATION]

    def tally(rows: list[dict]) -> dict:
        state = {"agreed": 0, "not_agreed": 0, "unknown": 0}
        for m in rows:
            agreed = (_intel(m).get("meeting") or {}).get("agreed")
            state["agreed" if agreed is True else "not_agreed" if agreed is False else "unknown"] += 1
        judged = state["agreed"] + state["not_agreed"]
        return {"conversations": len(rows), "judged": judged, **state, "meeting_rate_pct": round(state["agreed"] * 100 / judged, 1) if judged else None}

    body = tally(memos)
    reps = _rep_names(ctx, actor)
    if reps:
        by_rep = []
        for uid in sorted(reps, key=lambda u: reps[u].casefold()):
            rows = [m for m in memos if str(m.get("user_id")) == uid]
            if rows:
                by_rep.append({"rep": reps[uid], **tally(rows)})
        body["by_rep"] = by_rep
    judged = body["agreed"] + body["not_agreed"]
    return _envelope(n=len(memos), n_analysed=judged, period_days=days, period_defaulted=_defaulted(args), **body)


async def _playbook_lookup(args: dict, ctx, actor: AskActor) -> dict:
    from app.services.playbooks.live import live_snapshots

    snapshots = live_snapshots(ctx.supabase, actor.company_id)
    if not snapshots:
        return _envelope(n=0, n_analysed=0, coverage="complete", playbooks=[], evidence=[], note="no_playbook")
    category = str(args.get("category") or "").strip().lower()
    topic = str(args.get("topic") or "").strip().lower()
    out, evidence = [], []
    for view in snapshots:
        entries = []
        for entry in view["entries"]:
            hay = " ".join(str(entry.get(k) or "") for k in ("category", "guidance", "approved_answer")).lower()
            if (category and str(entry.get("category") or "").lower() != category) or (topic and topic not in hay):
                continue
            text = entry.get("approved_answer") or entry.get("guidance") or ""
            ev_id = f"pb-{entry.get('entry_id') or len(evidence)}"
            evidence.append({"id": ev_id, "quote": text, "speaker": "playbook", "rep": view["sales_motion_key"]})
            entries.append({"category": entry.get("category"), "answer": text, "evidence": ev_id})
        out.append({"motion": view["sales_motion_key"], "entries": entries, "steps": [s.get("label") for s in view["steps"] if isinstance(s, dict)]})
    return _envelope(n=len(out), n_analysed=len(out), coverage="complete", playbooks=out, evidence=evidence)


# ----- HubSpot tools --------------------------------------------------------------------------


def _is_forbidden(exc: Exception) -> bool:
    text = str(exc).lower()
    return "403" in text or "forbidden" in text or "scope" in text


async def _bundle_and_owner(ctx, actor: AskActor, args: dict, *, allow_by_rep: bool = False):
    """The HubSpot client and the owner filter the actor may use. Members are pinned to their own owner id."""
    from app.services.crm_copilot import tools as copilot_tools
    from app.services.hubspot.sync import _get_hubspot_owner_id_for_user, owner_id_from_connection_metadata

    if args.get("by_rep") and not (allow_by_rep and actor.is_team_reader):
        raise ScopeError("by_rep is for owners and admins")
    bundle = copilot_tools._crm(ctx)
    if not hasattr(bundle, "client"):  # Pipedrive: the HubSpot reads do not apply, and that is not "not connected"
        raise ValueError("not_available_for_pipedrive")
    requested = str(args.get("user_id") or "").strip() or None
    if not actor.is_team_reader:
        if requested and requested != actor.user_id:
            raise ScopeError("another user's numbers")
        target = actor.user_id
    else:
        target = requested
        if target:
            visible_user_ids(actor, _company(ctx, actor), target)
    if target is None:
        return bundle, None
    meta = bundle.connection.get("metadata") or {}
    owner = owner_id_from_connection_metadata(meta, target)
    if not owner:
        owner = await _get_hubspot_owner_id_for_user(bundle.client, ctx.supabase, target, bundle.connection.get("id"))
    if not owner:
        raise LookupError("owner_unresolved")
    return bundle, owner


def _with_default_period(args: dict, default_days: int) -> tuple[dict, bool]:
    """No period given: use the last N days, and let the answer say so."""
    if any(args.get(k) for k in ("month", "start_date", "period_days")):
        return args, False
    return {**args, "period_days": default_days}, True


def _crm_failure(exc: Exception) -> dict:
    """Say what actually went wrong. "CRM unavailable" means not connected; anything else is a different sentence."""
    if isinstance(exc, ScopeError):
        return dict(FORBIDDEN)
    if isinstance(exc, LookupError):
        return {"ok": False, "error": "owner_unresolved", "coverage": "unavailable"}
    if isinstance(exc, ValueError):
        text = str(exc)
        if text in ("No CRM connected", "crm_unavailable"):
            return dict(UNAVAILABLE)
        if text == "not_available_for_pipedrive":
            return {"ok": False, "error": text, "coverage": "unavailable"}
        return {"ok": False, "error": text}
    if isinstance(exc, HubSpotScopeError) or _is_forbidden(exc):
        return {"ok": False, "error": "forbidden", "coverage": "forbidden", "reason": "hubspot_scope"}
    if isinstance(exc, HubSpotAuthError):
        logger.warning("HubSpot rejected the token: %s", exc)
        return {"ok": False, "error": "hubspot_reconnect", "coverage": "unavailable"}
    if isinstance(exc, HubSpotRateLimitError):
        logger.warning("HubSpot rate limit after retries: %s", exc)
        return {"ok": False, "error": "hubspot_busy", "coverage": "unavailable", "retryable": True}
    if isinstance(exc, HubSpotValidationError):  # our request was wrong; the message helps the model fix it
        logger.warning("HubSpot rejected a request: %s", exc)
        return {"ok": False, "error": "hubspot_rejected", "detail": str(exc)[:240]}
    if isinstance(exc, HubSpotError):
        logger.warning("HubSpot request failed: %s", exc)
        return {"ok": False, "error": "hubspot_unreachable", "coverage": "unavailable", "retryable": True}
    logger.exception("Unexpected failure reading HubSpot for Ask")
    return {"ok": False, "error": "hubspot_error", "coverage": "unavailable"}


async def _previous_call_stats(client, current: dict, start, end, direction, owner, tz: str) -> dict:
    before_start, before_end = crm_query._previous_window(start, end, ZoneInfo(tz or "UTC"))
    before = await crm_analytics.call_stats(client, start=before_start, end=before_end, direction=direction, owner_id=owner)
    now_rate, was_rate = current.get("connection_rate_pct"), before.get("connection_rate_pct")
    return {
        "period": crm_analytics.local_span(before_start, before_end, tz), **before,
        "change_total_pct": crm_query._change_pct(current["total"], before["total"]),
        "change_rate_pts": round(now_rate - was_rate, 1) if now_rate is not None and was_rate is not None else None,
    }


async def _crm_call_stats(args: dict, ctx, actor: AskActor) -> dict:
    try:
        args, defaulted = _with_default_period(args, 30)
        start, end = crm_analytics.resolve_period(args, actor.timezone)
        bundle, owner = await _bundle_and_owner(ctx, actor, args, allow_by_rep=True)
        direction = {"inbound": "INBOUND", "all": None}.get(str(args.get("direction") or "outbound").lower(), "OUTBOUND")
        stats = await crm_analytics.call_stats(bundle.client, start=start, end=end, direction=direction, owner_id=owner)
        body: dict = {}
        if args.get("by_rep"):
            body["by_rep"] = await crm_analytics.call_stats_by_owner(bundle.client, start=start, end=end, direction=direction)
        if args.get("compare_previous"):
            body["previous"] = await _previous_call_stats(bundle.client, stats, start, end, direction, owner, actor.timezone)
    except Exception as exc:  # noqa: BLE001 - every failure becomes an honest coverage state
        return _crm_failure(exc)
    known = stats["total"] - stats["outcome_unknown"]
    coverage = "complete" if not stats["total"] or (stats["outcome_known_pct"] or 0) >= 70 else "partial"
    return _envelope(
        n=stats["total"], n_analysed=known, coverage=coverage, unit="calls",
        period=crm_analytics.local_span(start, end, actor.timezone), period_defaulted=defaulted, period_days=30, source="hubspot", **stats, **body,
    )


async def _crm_lost_reasons(args: dict, ctx, actor: AskActor) -> dict:
    try:
        args, defaulted = _with_default_period(args, 90)
        start, end = crm_analytics.resolve_period(args, actor.timezone)
        bundle, owner = await _bundle_and_owner(ctx, actor, args)
        top_n = max(1, min(int(args.get("top_n") or 5), 10))
        schema_service = bundle.provider._schema_service()
        configured = (bundle.connection.get("metadata") or {}).get("lost_reason_deal_property")
        out = await crm_analytics.lost_reasons(
            bundle.client, schema_service, start=start, end=end, top_n=top_n, owner_id=owner, configured_property=configured
        )
    except Exception as exc:  # noqa: BLE001
        return _crm_failure(exc)
    with_reason = out["fetched"] - (out["no_reason"] or 0)
    complete = out["reasons"] is not None and with_reason >= out["lost"]
    return _envelope(
        n=out["lost"], n_analysed=with_reason if out["reasons"] is not None else 0,
        coverage="complete" if complete or not out["lost"] else "partial", unit="deals",
        period=crm_analytics.local_span(start, end, actor.timezone), period_defaulted=defaulted, period_days=90, source="hubspot", **out,
    )


QUERY_MAX_SPAN_DAYS = 3650


def _query_period(args: dict, tz: str):
    if args.get("end_date") and not args.get("start_date"):
        raise crm_query.QueryError("bad_period", hint="end_date needs start_date; for 'before a date' use a filter on the date property (LT with an ISO date)")
    if any(args.get(k) for k in ("month", "start_date", "period_days")):
        try:
            return crm_analytics.resolve_period(args, tz, QUERY_MAX_SPAN_DAYS)
        except ValueError as exc:
            raise crm_query.QueryError("bad_period", hint=str(exc)) from exc
    return None


MAX_DESCRIBES_PER_TURN = 3


async def _hubspot_describe(args: dict, ctx, actor: AskActor) -> dict:
    ctx.describe_calls = getattr(ctx, "describe_calls", 0) + 1
    if ctx.describe_calls > MAX_DESCRIBES_PER_TURN:  # the model must not fish for a field that is not there
        return {"ok": False, "error": "describe_limit", "hint": "Stop looking. If none of the fields found answers the question, say it is not in HubSpot."}
    try:
        bundle, _ = await _bundle_and_owner(ctx, actor, {})
        out = await crm_query.describe(
            bundle.client, args.get("object_type"), search=args.get("search"), prop_name=args.get("property"),
            cache_key=str(bundle.connection.get("id") or ""),
        )
    except crm_query.QueryError as exc:
        return exc.payload()
    except Exception as exc:  # noqa: BLE001
        return _crm_failure(exc)
    if not actor.is_team_reader:  # owner options are the whole team's names
        for prop in [out.get("property") or {}, *(out.get("properties") or [])]:
            if prop.get("name") == crm_query.OWNER_PROPERTY:
                prop.pop("options", None)
                prop.pop("options_total", None)
    return {**out, "source": "hubspot"}


async def _hubspot_query(args: dict, ctx, actor: AskActor) -> dict:
    try:
        bundle, owner = await _bundle_and_owner(ctx, actor, args)
        out = await crm_query.run_query(
            bundle.client,
            object_type=args.get("object_type"),
            filters=args.get("filters"),
            period=_query_period(args, actor.timezone),
            date_property=args.get("date_property"),
            owner_id=owner,
            group_by=args.get("group_by"),
            date_bucket=args.get("date_bucket"),
            aggregate=args.get("aggregate") or "count",
            share_where=args.get("share_where"),
            compare_previous=bool(args.get("compare_previous")),
            metric_property=args.get("metric_property"),
            properties=args.get("properties"),
            sort_by=args.get("sort_by"),
            sort_dir=args.get("sort_dir"),
            limit=args.get("limit"),
            tz_name=actor.timezone,
            cache_key=str(bundle.connection.get("id") or ""),
        )
    except crm_query.QueryError as exc:
        return exc.payload()
    except Exception as exc:  # noqa: BLE001 - every failure becomes an honest coverage state
        return _crm_failure(exc)
    scope = "one rep" if owner and actor.is_team_reader else ("own records" if owner else "whole account")
    return _envelope(
        n=out.pop("n", 0), n_analysed=out.pop("n_analysed", 0), coverage=out.pop("coverage", None), unit=out.pop("unit", None) and "records",
        source="hubspot", scope=scope, period_given=out.get("period") is not None, **out,
    )


_HANDLERS = {
    "deal_story": _deal_story,
    "find_interactions": _find_interactions,
    "objection_breakdown": _objection_breakdown,
    "competitor_mentions": _competitor_mentions,
    "meetings_agreed": _meetings_agreed,
    "playbook_lookup": _playbook_lookup,
    "crm_call_stats": _crm_call_stats,
    "crm_lost_reasons": _crm_lost_reasons,
    "hubspot_describe": _hubspot_describe,
    "hubspot_query": _hubspot_query,
    **brain_tools.HANDLERS,
}


async def execute_intel_tool(name: str, args: dict, ctx: Any) -> dict:
    actor = getattr(ctx, "actor", None) or current_actor()
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "error": f"unknown tool {name}"}
    if name == "team_health" and not actor.is_team_reader:
        return dict(FORBIDDEN)
    try:
        return await handler(args or {}, ctx, actor)
    except ScopeError:
        return dict(FORBIDDEN)
