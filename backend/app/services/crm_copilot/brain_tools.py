"""The brain: what needs doing now, how a rep is doing against the company's own process, how the team is doing.

Each tool reads what the app's own screens read: Today's signals, the coaching engine behind the Coaching tab,
the team view behind the Head of Sales dashboard. One fact, one producer: Ask cannot say what a screen
contradicts, and it computes no second verdict. A proposal is built by rules from a fact (a promise, a silence,
an open objection); it names what to do, why and by when, and cites the playbook's answer when the company has
published one. Wording is the model's; content is data.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.services.crm_copilot.actor import AskActor, visible_user_ids
from app.services.crm_copilot.tool_schema import fn

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 60
MEMBER_ITEMS = 7
PER_REP_ITEMS = 2
MAX_REPS = 12
FORBIDDEN = {"ok": False, "error": "forbidden", "coverage": "forbidden"}
_CALL_KINDS = frozenset({"going_cold", "callback_no_answer", "never_contacted", "followup_due"})

VERDICT_MEANING = {
    "playbook_underperforms": "Reps who follow the playbook reach the goal less often than those who do not: the playbook needs review, not the reps.",
    "no_difference": "Following the playbook or not ends about the same: check which steps really help.",
    "coach_reps": "The playbook works, but it is followed in under half of interactions: an execution and coaching problem, not a playbook problem.",
    "playbook_works": "The playbook is followed and following it does better.",
    "no_comparison": "Almost every interaction follows the playbook, so there is no group to compare with.",
    "insufficient_data": "Too few scored interactions to conclude anything yet.",
    "goal_not_measurable": "This flow's goal shows in the CRM deal, not in a single conversation.",
}


def _base():
    """The shared helpers live in intel_tools, which imports this module: resolve them at call time."""
    from app.services.crm_copilot import intel_tools

    return intel_tools


def _pct(rate: Optional[float]) -> Optional[float]:
    return None if rate is None else round(rate * 100, 1)


def _day(value: Optional[datetime], tz_name: str) -> Optional[str]:
    if value is None:
        return None
    from zoneinfo import ZoneInfo

    return value.astimezone(ZoneInfo(tz_name or "UTC")).date().isoformat()


# ----- the company's published answers -----------------------------------------------------------


def published_answers(ctx, actor: AskActor) -> tuple[dict[str, dict], list[dict]]:
    """{objection category: {answer, evidence, motion}} from the published playbooks, plus the citable entries.
    ({}, []) when there is none or the read fails: no answer is ever made up."""
    from app.services.playbooks.live import live_snapshots

    try:
        snapshots = live_snapshots(ctx.supabase, actor.company_id)
    except Exception:  # noqa: BLE001
        return {}, []
    answers: dict[str, dict] = {}
    evidence: list[dict] = []
    for view in snapshots:
        for entry in view["entries"]:
            category = str(entry.get("category") or "").strip().lower()
            text = " ".join(str(entry.get("approved_answer") or entry.get("guidance") or "").split())
            if not category or not text or category in answers:
                continue
            ev_id = f"pb-{entry.get('entry_id') or category}"
            answers[category] = {"answer": text, "evidence": ev_id, "motion": view["sales_motion_key"]}
            evidence.append({"id": ev_id, "quote": text, "speaker": "playbook", "rep": view["sales_motion_key"], "category": category})
    return answers, evidence


# ----- next_actions -------------------------------------------------------------------------------


def _signal_from_row(row: dict):
    from app.services.hoy.signals import Signal

    payload = dict(row.get("payload") or {})
    raw_due = payload.get("due_at")
    due_at = None
    if isinstance(raw_due, str) and raw_due:
        try:
            due_at = datetime.fromisoformat(raw_due.replace("Z", "+00:00"))
        except ValueError:
            due_at = None
    return Signal(
        type=row["type"], contact_id=row.get("contact_id"), deal_id=row.get("deal_id"), source_memo_id=row.get("memo_id") or "",
        due_at=due_at, payload=payload, dedupe_key=row["dedupe_key"], connection_id=row.get("connection_id"),
    )


def _collect_signals(ctx, actor: AskActor, user_ids: list[str], memos: list[dict], now: datetime) -> tuple[list, dict[str, str]]:
    """What Today would show: its stored cards that are still visible, plus fresh ones it has not stored yet.
    A card the rep dismissed or closed there stays hidden here. {dedupe_key: user_id} says whose each one is."""
    from app.services.hoy.materialize import day_end, fresh_signals
    from app.services.hoy.visibility import is_today_visible

    stored: list[dict] = []
    try:
        stored = ctx.supabase.table("action_signals").select("*").eq("company_id", actor.company_id).in_("user_id", user_ids).execute().data or []
    except Exception:  # noqa: BLE001 - the stored cards are a refinement; fresh ones still answer
        logger.warning("action_signals unreadable for Ask", exc_info=True)
    owner: dict[str, str] = {}
    signals = []
    for row in stored:
        if row.get("type") == "confirm_pending" or not is_today_visible(row, now):
            continue
        signal = _signal_from_row(row)
        signals.append(signal)
        owner[signal.dedupe_key] = str(row.get("user_id") or "")
    known = {str(row.get("dedupe_key") or "") for row in stored}
    by_user: dict[str, list[dict]] = {}
    for memo in memos:
        by_user.setdefault(str(memo.get("user_id") or ""), []).append(memo)
    for uid, group in by_user.items():
        for signal in fresh_signals(group, now=now, day_end=day_end(now, actor.timezone)):
            if signal.dedupe_key not in known:
                signals.append(signal)
                owner[signal.dedupe_key] = uid
    return signals, owner


def _memo_evidence(memo: dict, kind: str, match: str, rep: Optional[str]) -> Optional[dict]:
    """The quote behind a card, when the memo's own facts carry one: the open objection of that category, or
    the promise with that text."""
    base = _base()
    intel = base._intel(memo)
    refs: list[str] = []
    if kind == "objection":
        for e in base._episodes(memo):
            if e["kind"] == "objection" and e["category"] == match and e["state"] in ("open", "unknown") and e["evidence_refs"]:
                refs = e["evidence_refs"][:1]
                break
    else:
        for item in intel.get("commitments") or []:
            if isinstance(item, dict) and str(item.get("text") or "").strip() == match and item.get("evidence_refs"):
                refs = list(item["evidence_refs"])[:1]
                break
    found = base._evidence_items(memo, set(refs), rep) if refs else []
    return found[0] if found else None


def _suggest(signal, now: datetime, tz_name: str, answers: dict[str, dict]) -> dict:
    """What to do about a card, by rule. Structure only: the model words it, the data supplies the substance."""
    p, kind = signal.payload, signal.type
    if kind == "commitment_due":
        due = signal.due_at
        return {
            "do": "keep_promise" if p.get("origin") == "rep_promise" else "answer_request",
            "action": p.get("kind") or "other", "what": p.get("text"), "by": _day(due, tz_name),
            "overdue": bool(due and due < now),
        }
    if kind == "objection_open":
        category = str(p.get("category") or "other")
        found = answers.get(category)
        return {"do": "answer_objection", "category": category, "quote": p.get("quote"), **({"playbook": found} if found else {"playbook": None})}
    if kind == "going_cold":
        return {"do": "reach_out", "action": "call", "interest": p.get("interest"), "days_silent": p.get("days_silent")}
    if kind == "callback_no_answer":
        return {"do": "call_back", "action": "call"}
    if kind == "never_contacted":
        return {"do": "first_call", "action": "call"}
    if kind == "no_reply":
        return {"do": "nudge", "action": "email"}
    if kind == "meeting_today":
        return {"do": "prepare_meeting", "action": "meeting"}
    if kind == "followup_due":
        return {"do": "follow_up", "action": "call"}
    return {"do": "review"}


def _describe(signal, memo: dict, rep: Optional[str], now: datetime, actor: AskActor, answers: dict, team_view: bool) -> tuple[dict, Optional[dict]]:
    """One signal as the model needs it: what to do (by rule), the quote behind it, and, off the team view, the
    sentence Today shows for it (addressed to the rep: 'you promised')."""
    from app.services.hoy.reasons import reason

    suggestion = _suggest(signal, now, actor.timezone, answers)
    quote = None
    if signal.type == "objection_open":
        quote = _memo_evidence(memo, "objection", str(signal.payload.get("category") or "other"), rep)
    elif signal.type == "commitment_due":
        quote = _memo_evidence(memo, "commitment", str(signal.payload.get("text") or "").strip(), rep)
    described = {
        "type": signal.type, "due": _day(signal.due_at, actor.timezone), "suggested": suggestion,
        **({} if team_view else {"why": reason(signal, lang=actor.locale, lead_tiers=True, now=now)}),
        **({"evidence": quote["id"]} if quote else {}),
    }
    if not described.get("why"):
        described.pop("why", None)
    return described, quote


async def _next_actions(args: dict, ctx, actor: AskActor) -> dict:
    from app.services.hoy.names import lookup, memo_directory
    from app.services.hoy.signals import rank_cards

    base = _base()
    requested = str(args.get("user_id") or "").strip() or None
    user_ids = visible_user_ids(actor, base._company(ctx, actor), requested)
    now = datetime.now(timezone.utc)
    memos = base._load_memos(ctx, actor, user_ids, since=now - timedelta(days=LOOKBACK_DAYS), limit=200)
    signals, owner = _collect_signals(ctx, actor, user_ids, memos, now)
    reps = base._rep_names(ctx, actor)
    by_id = {str(m["id"]): m for m in memos}
    directory = memo_directory(memos)
    answers, pb_evidence = published_answers(ctx, actor)
    team_view = actor.is_team_reader and not requested and len(user_ids) > 1
    limit = PER_REP_ITEMS if team_view else max(1, min(int(args.get("limit") or MEMBER_ITEMS), MEMBER_ITEMS))

    grouped: dict[str, list] = {}
    for signal in signals:
        grouped.setdefault(owner.get(signal.dedupe_key, ""), []).append(signal)
    items: list[dict] = []
    evidence: list[dict] = []
    folded = 0
    for uid in sorted(grouped, key=lambda u: (reps.get(u) or u).casefold())[:MAX_REPS]:
        cards, more = rank_cards(grouped[uid], now=now, limit=limit)
        folded += more
        for card in cards:
            primary = card.primary
            memo = by_id.get(primary.source_memo_id) or {}
            name, company = lookup(directory, primary.source_memo_id, primary.contact_id)
            contact = f"{name} ({company})" if name and company else name or company
            head, head_quote = _describe(primary, memo, reps.get(uid), now, actor, answers, team_view)
            also = []
            for other in card.supporting:
                detail, quote = _describe(other, by_id.get(other.source_memo_id) or memo, reps.get(uid), now, actor, answers, team_view)
                also.append(detail)
                evidence += [quote] if quote else []
            evidence += [head_quote] if head_quote else []
            items.append({
                "contact": contact, "contact_id": primary.contact_id, **({"rep": reps[uid]} if reps.get(uid) else {}),
                **head, **({"also": also} if also else {}),
            })
    cited = {ref for i in items for d in [i, *i.get("also", [])] for ref in [(d["suggested"].get("playbook") or {}).get("evidence")] if ref}
    evidence += [e for e in pb_evidence if e["id"] in cited]
    counts: dict[str, int] = {}
    for signal in signals:
        counts[signal.type] = counts.get(signal.type, 0) + 1
    _record_call_targets(ctx, actor, items, team_view)
    analysed = sum(1 for m in memos if base._intel(m))
    return base._envelope(
        n=len(memos), n_analysed=analysed, counts=counts, items=items, more=folded,
        obstacles=base._open_obstacles(memos, reps), evidence=evidence,
        playbook_published=bool(answers) or None,
    )


def _record_call_targets(ctx, actor: AskActor, items: list[dict], team_view: bool) -> None:
    """Contacts to call now, as data the panel turns into Call buttons (never from the model's text). Own list only."""
    if team_view:
        return
    try:
        from app.services.crm_copilot.call_actions import call_targets, record_call_targets
        from app.services.crm_providers import resolve_sync_connection_prefer_hubspot

        rows = [
            {"contact_id": i["contact_id"], "contact_name": i.get("contact"), "reason": i.get("why") or i["type"], "next_action": "call"}
            for i in items
            if i.get("contact_id") and (i["suggested"].get("action") == "call" or i["type"] in _CALL_KINDS)
        ]
        if not rows:
            return
        connection = resolve_sync_connection_prefer_hubspot(ctx.supabase, actor.user_id)
        if not connection:
            return
        for row in rows:
            row["connection_id"] = connection.get("id")
        record_call_targets(ctx, call_targets(rows, provider=str(connection.get("provider") or "").lower() or None, connection=connection))
    except Exception:  # noqa: BLE001 - a Call button is a courtesy, never a failure
        logger.info("call targets skipped", exc_info=True)


# ----- cards --------------------------------------------------------------------------------------


def record_card(ctx, card: dict) -> None:
    """What the Coach or Team screen shows, taken from the same producer, for Ask to draw under its answer.
    Turn-scoped, one per kind: the last read of the turn wins. Never built from the model's words."""
    try:
        ctx.cards = [*(c for c in (getattr(ctx, "cards", None) or []) if c.get("kind") != card["kind"]), card]
    except Exception:  # noqa: BLE001 - a card is a courtesy, never a failure
        pass


def _coaching_card(body: dict) -> dict:
    return {
        "kind": "coaching", "flow": body.get("flow"), "focus": body.get("focus"),
        "steps": body.get("steps") or [], "conversion": body.get("conversion"),
    }


def _team_card(body: dict, previous: dict, period: str, one_rep: bool) -> dict:
    keys = ("motion", "goal", "scored", "verdict", "follow_share", "follows_goal_rate", "deviates_goal_rate", "needed")
    reps = []
    for rep in body.get("reps") or []:
        focus = rep.get("coaching_focus") or None
        reps.append({
            "user_id": rep.get("userId"), "name": rep.get("name"),
            "focus": {"label": focus.get("label"), "rate": focus.get("rate")} if focus else None,
        })
    reps.sort(key=lambda r: str(r["name"] or "").casefold())
    return {
        "kind": "team", "period": period, "one_rep": one_rep,
        "adherence": body.get("adherence"), "previous": previous.get("adherence"),
        "process": [{k: flow.get(k) for k in keys} for flow in body.get("process_health") or []],
        "reps": reps[:MAX_REPS], "more_reps": max(0, len(reps) - MAX_REPS),
    }


# ----- my_coaching --------------------------------------------------------------------------------


def _membership(actor: AskActor):
    """The caller as the screens' own endpoints see them, built from the actor the server already resolved."""
    from app.services.company import Membership

    return Membership(
        id="", company_id=actor.company_id, user_id=actor.user_id, role=actor.role, status="active",
        sales_role=actor.sales_role, visibility=actor.visibility or "own",
    )


async def _my_coaching(args: dict, ctx, actor: AskActor) -> dict:
    from app.api import coaching as coaching_api

    base = _base()
    membership = _membership(actor)
    flow = str(args.get("flow") or "").strip().lower() or None
    flow = flow if flow in ("sdr", "ae") else None
    try:
        body = await coaching_api.get_my_coaching_summary(flow=flow, membership=membership, supabase=ctx.supabase)
    except HTTPException as error:
        return {"ok": False, "error": "no_coaching_flow", "coverage": "unavailable", "detail": str(error.detail)}
    except Exception:  # noqa: BLE001
        logger.exception("coaching summary failed for Ask")
        return {"ok": False, "error": "coaching_unavailable", "coverage": "unavailable"}
    numbers = body.get("numbers") or {}
    out: dict[str, Any] = {
        "flow": body.get("flow"), "playbook_published": bool(body.get("playbook_published")), "week_from": body.get("week_start"),
        "this_week": numbers, "last_week": body.get("prev_numbers") or {},
    }
    if not body.get("playbook_published"):
        return base._envelope(n=numbers.get("conversations") or 0, n_analysed=0, coverage="partial", note="no_published_playbook", **out)
    record_card(ctx, _coaching_card(body))
    out["steps"] = [
        {
            "step": s["label"], "rate_pct": _pct(s.get("rate")), "last_week_pct": _pct(s.get("prev_rate")),
            "team_median_pct": _pct(s.get("peer_median")),
        }
        for s in body.get("steps") or []
    ]
    focus = body.get("focus")
    if focus:
        why = focus.get("why") or {}
        total = focus.get("week_total") or {}
        out["focus"] = {
            "step": focus["label"], "criterion": focus.get("criterion") or None, "example": focus.get("example") or None,
            "last_week_pct": _pct(why.get("rate")), "conversations": why.get("applicable"), "missed_in": why.get("missing"),
            "team_median_pct": _pct(why.get("peer_median")),
            "this_week": {"done": total.get("done"), "of": total.get("applicable"), "pct": _pct(total.get("rate"))},
            "achieved": bool(focus.get("achieved")),
        }
    else:
        out["focus"] = None
        out["focus_note"] = "No step repeats as a miss: nothing to focus on this week."
    conversion = body.get("conversion")
    if conversion:
        out["conversion"] = {
            "meeting_rate_full_process_pct": _pct(conversion.get("complete_rate")), "meeting_rate_with_gaps_pct": _pct(conversion.get("incomplete_rate")),
            "conversations_full_process": conversion.get("complete_n"), "conversations_with_gaps": conversion.get("incomplete_n"),
        }
    conversations = numbers.get("conversations") or 0
    return base._envelope(n=conversations, n_analysed=conversations, coverage="complete", **out)


# ----- team_health --------------------------------------------------------------------------------


async def _team_health(args: dict, ctx, actor: AskActor) -> dict:
    from app.api import team_insights as team_api
    from app.services.crm_copilot import crm_analytics

    base = _base()
    if not actor.is_team_reader:
        return dict(FORBIDDEN)
    membership = _membership(actor)
    period = str(args.get("period") or "last_30").strip()
    period = period if period in ("week", "month", "last_30", "quarter") else "last_30"
    requested = str(args.get("user_id") or "").strip() or None
    if requested:
        visible_user_ids(actor, base._company(ctx, actor), requested)
    sales_role = str(args.get("sales_role") or "").strip().lower() or None
    include = {str(x).strip().lower() for x in (args.get("include") or []) if isinstance(x, str)}
    try:
        response = await team_api.get_team_adherence(
            user_id=requested, motion=None, period=period, sales_role=sales_role if sales_role in ("sdr", "ae") else None,
            with_focus=True, membership=membership, supabase=ctx.supabase,
        )
        body = json.loads(response.body)
    except HTTPException as error:
        return dict(FORBIDDEN) if error.status_code == 403 else {"ok": False, "error": "team_health_unavailable", "coverage": "unavailable"}
    except Exception:  # noqa: BLE001
        logger.exception("team health failed for Ask")
        return {"ok": False, "error": "team_health_unavailable", "coverage": "unavailable"}
    tz = actor.timezone
    span = body.get("period") or {}
    previous = body.get("previous") or {}
    adherence, before = body.get("adherence"), previous.get("adherence")
    process = []
    for flow in body.get("process_health") or []:
        verdict = flow.get("verdict")
        process.append({
            "flow": flow.get("motion"), "goal": flow.get("goal"), "verdict": verdict, "meaning": VERDICT_MEANING.get(verdict),
            "interactions_scored": flow.get("scored"),
            "goal_reached_pct_when_playbook_followed": _pct(flow.get("follows_goal_rate")),
            "goal_reached_pct_when_not_followed": _pct(flow.get("deviates_goal_rate")),
            "interactions_following_playbook_pct": _pct(flow.get("follow_share")),
            **({"needs_more": flow["needed"]} if flow.get("needed") else {}),
        })
    reps = []
    for rep in body.get("reps") or []:
        focus = rep.get("coaching_focus") or None
        activity = rep.get("activity") or {}
        reps.append({
            "name": rep.get("name"), "role": rep.get("salesRole"), "attempts": activity.get("attempts"),
            "connected": activity.get("connected"), "meetings": activity.get("meetings"),
            "adherence_by_flow_pct": {k: _pct(v) for k, v in (rep.get("flows") or {}).items()},
            "focus": {"step": focus.get("label"), "rate_pct": _pct(focus.get("rate"))} if focus else None,
        })
    reps.sort(key=lambda r: str(r["name"] or "").casefold())  # a breakdown, never a ranking
    objections = [
        {"category": o.get("name"), "total": o.get("count"), "open": o.get("open"), "resolved": o.get("resolved"), "unknown": o.get("unknown")}
        for o in (body.get("objection_categories") or [])[:5]
    ]
    playbook = bool(body.get("applicable_steps"))
    if playbook:
        record_card(ctx, _team_card(body, previous, period, bool(requested)))
    complete = adherence is not None and not body.get("sample_limited")
    out = {
        "ok": True, "scope": "one rep" if requested else "whole team", "period_key": period, "period": None,
        "adherence_pct": _pct(adherence), "adherence_last_period_pct": _pct(before),
        "adherence_change_pts": round((adherence - before) * 100, 1) if adherence is not None and before is not None else None,
        "steps_met": body.get("met_steps"), "steps_applicable": body.get("applicable_steps"), "sample_limited": bool(body.get("sample_limited")),
        "process": process, "reps": reps[:MAX_REPS],
        **({"activity": {"attempts": body.get("attempts"), "connected": body.get("connected"), "meetings": body.get("meetings")}} if "activity" in include else {}),
        **({"activity_last_period": {"attempts": previous.get("attempts"), "connected": previous.get("connected"), "meetings": previous.get("meetings")}} if previous and "activity" in include else {}),
        **({"objections": objections} if "objections" in include else {}),
        **({"won": body.get("won"), "lost": body.get("lost")} if body.get("won") is not None or body.get("lost") is not None else {}),
        **({} if playbook else {"note": "no_scored_conversations_or_no_published_playbook"}),
    }
    if span.get("start") and span.get("end"):
        try:
            out["period"] = crm_analytics.local_span(datetime.fromisoformat(span["start"]), datetime.fromisoformat(span["end"]), tz)
        except ValueError:
            pass
    return base._envelope(
        n=body.get("applicable_steps") or 0, n_analysed=body.get("applicable_steps") or 0,
        coverage="complete" if complete else "partial", unit="steps", **out,
    )


# ----- registration ------------------------------------------------------------------------------

_USER = {"type": "string", "description": "One team member's user id (managers only)."}

MEMBER_TOOLS = [
    fn(
        "next_actions",
        "What needs doing now, ranked, each with the suggested next step: promises due or overdue, contacts going quiet, "
        "open objections (with the playbook's approved answer when there is one), callbacks, meetings today. The same "
        "list Today shows. A rep sees their own; managers see each rep's top items, or one rep with user_id. For 'what "
        "should I do today', 'what is due', 'who do I follow up'.",
        {"user_id": _USER, "limit": {"type": "integer", "description": "1-7. Default 7."}},
    ),
    fn(
        "my_coaching",
        "How the caller is doing against the company's own sales process: this week's one focus step, every step's rate "
        "against last week and the team median, and whether following the process converts for them. Only the caller's "
        "own data. For 'how am I doing', 'what should I improve', 'what is my focus'. Not for the team.",
        {"flow": {"type": "string", "enum": ["sdr", "ae"], "description": "Only for a rep without a fixed sales role."}},
    ),
]

TEAM_TOOLS = [
    fn(
        "team_health",
        "Is the team's problem the people or the process? Playbook adherence and its change vs the previous period, whether "
        "following the playbook reaches the goal (coach the reps, or fix the playbook), activity and each rep's coaching "
        "focus (alphabetical), top objections. For 'how is the team doing', 'do we need coaching or a new playbook', "
        "'who needs help with what'.",
        {
            "period": {"type": "string", "enum": ["week", "month", "last_30", "quarter"], "description": "Default last_30."},
            "user_id": _USER,
            "sales_role": {"type": "string", "enum": ["sdr", "ae"]},
            "include": {
                "type": "array", "items": {"type": "string", "enum": ["activity", "objections"]},
                "description": "Only when the question asks for them: call activity, top objections. Default: adherence, verdicts and each rep's focus.",
            },
        },
    ),
]

HANDLERS = {"next_actions": _next_actions, "my_coaching": _my_coaching, "team_health": _team_health}
