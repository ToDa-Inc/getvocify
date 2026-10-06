"""Turn stored memo intelligence into Hoy signals. No model call."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.hoy.heat import heat_score
from app.services.hoy.memo_facts import _pain
from app.services.hoy.signals import (
    DEFAULT_LIMIT,
    Signal,
    Touch,
    never_contacted_signal,
    screening_from_call,
    signals_for_contact,
    touch_from_intelligence,
)
from app.services.intelligence import extract


HOY_MEMO_LIMIT = 40
HOY_CALL_LIMIT = 200
DEFAULT_CALLBACK_AFTER_DAYS = 2
# outbound_calls.call_disposition values (027_call_screening.sql) that mean "no
# conversation happened" - broader than memos.screening_outcome's UNANSWERED_OUTCOMES
# because a missed call never gets a memo at all (screening only runs on a connected
# recording), so this is the only signal an unanswered dial ever leaves behind.
UNANSWERED_CALL_DISPOSITIONS: frozenset[str] = frozenset({"no_response", "voicemail", "busy", "no_answer"})


def as_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _intelligence(memo: dict) -> dict:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    block = extraction.get("intelligence")
    return block if isinstance(block, dict) else {}


def _objections(extraction: dict, intelligence: dict, *, current: bool) -> list[dict]:
    c04 = intelligence.get("objections")
    # An empty list from current C04 means "no objection"; from a stale run it proves nothing.
    trusted = isinstance(c04, list) and (bool(c04) or current)
    raw = c04 if trusted else extraction.get("objections") or []
    open_rows: list[dict] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                open_rows.append({"state": "open", "category": "other", "quote": text[:160]})
            continue
        if not isinstance(item, dict):
            continue
        if item.get("commercial_objection") is False or item.get("kind") == "obstacle":
            continue  # a practical block is a follow-up, not an objection (see open_loops in Ask)
        state = item.get("state") or item.get("resolution") or "open"
        if state not in {"open", "unknown"}:
            continue
        open_rows.append({
            "state": "open",
            "category": item.get("category") or "other",
            "quote": item.get("quote") or item.get("text") or "",
        })
    return open_rows


def _commitments(intelligence: dict) -> list[dict]:
    kept: list[dict] = []
    for item in intelligence.get("commitments") or []:
        if isinstance(item, dict) and item.get("due_at") and item.get("text"):
            kept.append(item)
    return kept


def fresh_signals(
    memos: list[dict],
    *,
    now: datetime,
    day_end: datetime,
    ignore_deal_closed: bool = False,
) -> list:
    """One contact, one set of signals, from intelligence already on the memo."""
    groups: dict[str, list] = {}
    pain_by_memo: dict[str, bool] = {}
    for memo in memos:
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        intelligence = _intelligence(memo)
        shaped = {
            **intelligence,
            "objections": _objections(extraction, intelligence, current=bool(intelligence) and extract.is_current(memo)),
            "commitments": _commitments(intelligence),
        }
        at = as_dt(memo.get("capture_started_at") or memo.get("created_at"))
        contact = memo.get("hubspot_contact_id") or memo.get("contact_id")
        memo_id = str(memo.get("id") or "")
        pain_by_memo[memo_id] = _pain(extraction) or intelligence.get("pain_confirmed") is True
        touch = touch_from_intelligence(
            memo_id=memo_id,
            contact_id=str(contact) if contact else None,
            deal_id=str(memo.get("hubspot_deal_id")) if memo.get("hubspot_deal_id") else None,
            at=at,
            connection_id=memo.get("connection_id"),
            intelligence=shaped if shaped.get("objections") or shaped.get("commitments") or shaped.get("interest") else None,
            history_complete=True,
            screening_outcome=screening_from_call(memo.get("screening_outcome"), intelligence),
            followup_at=_stored_followup_at(memo),
            rep_outcome=memo.get("rep_outcome"),
        )
        if touch is None:
            continue
        groups.setdefault(touch.contact_id or touch.memo_id, []).append(touch)
    return groups, pain_by_memo


def contact_touches(memos: list[dict]) -> tuple[dict[str, list], dict[str, bool]]:
    """Each contact's touches, read off the intelligence already on its memos, and whether
    each memo confirmed pain (heat reads it)."""
    groups: dict[str, list] = {}
    pain_by_memo: dict[str, bool] = {}
    for memo in memos:
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        intelligence = _intelligence(memo)
        shaped = {
            **intelligence,
            "objections": _objections(extraction, intelligence, current=bool(intelligence) and extract.is_current(memo)),
            "commitments": _commitments(intelligence),
        }
        at = as_dt(memo.get("capture_started_at") or memo.get("created_at"))
        contact = memo.get("hubspot_contact_id") or memo.get("contact_id")
        memo_id = str(memo.get("id") or "")
        pain_by_memo[memo_id] = _pain(extraction) or intelligence.get("pain_confirmed") is True
        touch = touch_from_intelligence(
            memo_id=memo_id,
            contact_id=str(contact) if contact else None,
            deal_id=str(memo.get("hubspot_deal_id")) if memo.get("hubspot_deal_id") else None,
            at=at,
            connection_id=memo.get("connection_id"),
            intelligence=shaped if shaped.get("objections") or shaped.get("commitments") or shaped.get("interest") else None,
            history_complete=True,
            screening_outcome=screening_from_call(memo.get("screening_outcome"), intelligence),
            followup_at=_stored_followup_at(memo),
            rep_outcome=memo.get("rep_outcome"),
        )
        if touch is None:
            continue
        groups.setdefault(touch.contact_id or touch.memo_id, []).append(touch)
    return groups, pain_by_memo


HANDOFF_FOLLOWUP_KEY_PREFIX = "followup:handoff:"


def handoff_touches(handoffs: list[dict], sdr_memos: list[dict], *, own_contact_ids: set[str]) -> list[tuple[dict, Touch]]:
    """Lista 4 T8 (E13): a contact handed to this AE that the AE has no memo about yet comes
    back on the cadence of the SDR's last conversation, counted from the handoff meeting (or,
    without one, from the handoff itself). Each pair is (handoff, touch): the SDR's latest
    touch on that contact with `at` moved to that moment. The SDR's own date, outcome
    (meeting_booked) and commitments are the SDR's, not the AE's, so they are dropped."""
    sdr_groups, _pain = contact_touches(sdr_memos)
    memo_ids_by_user: dict[str, set[str]] = {}
    for memo in sdr_memos:
        memo_ids_by_user.setdefault(str(memo.get("user_id") or ""), set()).add(str(memo.get("id") or ""))
    out: list[tuple[dict, Touch]] = []
    for handoff in handoffs:
        contact_id = str(handoff.get("contact_id") or "")
        if not contact_id or not handoff.get("id") or contact_id in own_contact_ids:
            continue
        # Only the handing-off SDR's memos: another rep's note about the same contact is not
        # the conversation that led to this handoff.
        sdr_memo_ids = memo_ids_by_user.get(str(handoff.get("sdr_user_id") or ""), set())
        touches = [touch for touch in sdr_groups.get(contact_id, []) if touch.memo_id in sdr_memo_ids]
        anchor = as_dt(handoff.get("meeting_starts_at")) or as_dt(handoff.get("created_at"))
        if not touches or anchor is None:
            continue
        last = max(touches, key=lambda t: t.at)
        if last.deal_closed:
            continue
        out.append((handoff, replace(
            last,
            at=anchor,
            deal_id=str(handoff.get("deal_id")) if handoff.get("deal_id") else last.deal_id,
            connection_id=str(handoff.get("connection_id") or "") or last.connection_id,
            commitments=(),
            followup_at=None,
            rep_outcome=None,
            screening_outcome=None,
        )))
    return out


def handoff_followup_signals(
    handoffs: list[dict],
    sdr_memos: list[dict],
    *,
    own_contact_ids: set[str],
    now: datetime,
    day_end: datetime,
    cadence: dict[str, int],
) -> list[Signal]:
    """followup_due for handed-off contacts the AE has not talked to yet (handoff_touches),
    keyed per handoff and due day so a dismissal holds and the AE's first memo retracts it."""
    out: list[Signal] = []
    for handoff, touch in handoff_touches(handoffs, sdr_memos, own_contact_ids=own_contact_ids):
        for signal in signals_for_contact([touch], now=now, day_end=day_end, cadence=cadence):
            if signal.type != "followup_due" or signal.due_at is None:
                continue
            out.append(replace(
                signal,
                payload={**signal.payload, "handoff_id": str(handoff["id"])},
                dedupe_key=f"{HANDOFF_FOLLOWUP_KEY_PREFIX}{handoff['id']}:{signal.due_at.date().isoformat()}",
            ))
    return out


def fresh_signals(
    memos: list[dict],
    *,
    now: datetime,
    day_end: datetime,
    lead_tiers_enabled: bool = False,
    callback_after_days: int = DEFAULT_CALLBACK_AFTER_DAYS,
    cadence: dict[str, int] | None = None,
) -> list:
    """One contact, one set of signals, from intelligence already on the memo.

    `lead_tiers_enabled` is HOY_LEAD_TIERS_ENABLED for a SDR/General rep (T5): off, this
    is byte-identical to before (no callback_no_answer, no heat on the payload).
    `cadence` is HOY_SDR_SECTIONS_ENABLED's company overrides (Lista 4 T2), None when off."""
    groups, pain_by_memo = contact_touches(memos)
    signals = []
    for touches in groups.values():
        signals.extend(
            signals_for_contact(touches, now=now, day_end=day_end, ignore_deal_closed=ignore_deal_closed)
        )
    return signals


def never_contacted_signals(
    candidates: list[dict],
    *,
    touched_contact_ids: set[str],
    limit: int = DEFAULT_LIMIT,
) -> list[Signal]:
    """T5 review: `candidates` is `priority.rank_candidates`'s own output (already
    caller-owned and unambiguous, meeting-agreed/closed-deal already dropped). It reuses
    that function's `never_called` flag rather than re-deriving the rule, so "contacted"
    being unknown (None) never counts as "never contacted" and a partial-coverage row
    never does either - both are `rank_candidates`'s job, already tested there.
    Ephemeral: never persisted, so no dedupe/retraction is needed here."""
    out: list[Signal] = []
    for row in candidates:
        if not row.get("never_called"):
            continue
        contact_id = str(row.get("contact_id") or "")
        if not contact_id or contact_id in touched_contact_ids:
            continue
        out.append(never_contacted_signal(
            contact_id=contact_id,
            connection_id=row.get("connection_id"),
            deal_id=row.get("deal_id"),
            contact_name=row.get("contact_name"),
        ))
        if len(out) >= limit:
            break
    return out


def contact_last_touch_at(memos: list[dict]) -> dict[str, datetime]:
    """The latest memo timestamp per contact - used to tell a missed call apart from one
    that already has a later, real conversation on record."""
    latest: dict[str, datetime] = {}
    for memo in memos:
        contact = memo.get("hubspot_contact_id") or memo.get("contact_id")
        if not contact:
            continue
        at = as_dt(memo.get("capture_started_at") or memo.get("created_at"))
        if at is None:
            continue
        key = str(contact)
        if key not in latest or at > latest[key]:
            latest[key] = at
    return latest


def read_hoy_calls(supabase, *, user_id: str) -> list[dict]:
    """The rep's newest placed calls (missed ones never get a memo, so this is the only
    record of them). Tolerant of the table itself being unavailable."""
    try:
        stored = (
            supabase.table("outbound_calls")
            .select("id,hubspot_contact_id,hubspot_deal_id,call_disposition,created_at,to_number")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(HOY_CALL_LIMIT)
            .execute()
        )
    except Exception:
        return []
    return list(stored.data or [])


def callback_no_answer_from_calls(
    calls: list[dict],
    *,
    last_touch_at: dict[str, datetime],
    now: datetime,
    callback_after_days: int,
) -> list[Signal]:
    """T5 review: most unanswered calls never produce a memo at all (screening only runs
    on a connected recording), so callback_no_answer must also come straight from
    outbound_calls - the latest attempt per contact, and only when nothing later (another
    call or a memo) already supersedes it."""
    latest: dict[str, dict] = {}
    for call in calls:
        contact = call.get("hubspot_contact_id")
        if not contact:
            continue
        at = as_dt(call.get("created_at"))
        if at is None:
            continue
        key = str(contact)
        current = latest.get(key)
        if current is None or at > current["at"]:
            latest[key] = {"at": at, "call": call}
    out: list[Signal] = []
    for contact_id, entry in latest.items():
        at = entry["at"]
        call = entry["call"]
        disposition = str(call.get("call_disposition") or "")
        if disposition not in UNANSWERED_CALL_DISPOSITIONS:
            continue
        newer_touch = last_touch_at.get(contact_id)
        if newer_touch is not None and newer_touch >= at:
            continue
        if now - at < timedelta(days=callback_after_days):
            continue
        call_id = str(call.get("id") or "")
        if not call_id:
            continue
        out.append(Signal(
            "callback_no_answer",
            contact_id=contact_id,
            deal_id=str(call.get("hubspot_deal_id")) if call.get("hubspot_deal_id") else None,
            source_memo_id="",
            due_at=None,
            # The number dialled names the card when no call ever gave us the contact's name.
            payload={"outcome": disposition, "at": at.isoformat(),
                     **({"phone": str(call["to_number"])} if call.get("to_number") else {})},
            dedupe_key=f"callback:call:{call_id}",
            connection_id=None,
        ))
    return out


def exclude_handoff_contacts(signals: list[Signal], handoff_contact_ids: set[str]) -> list[Signal]:
    """T5 (D6/T3): a contact under an active SDR->AE handoff leaves the SDR's Hoy."""
    if not handoff_contact_ids:
        return signals
    return [signal for signal in signals if signal.contact_id not in handoff_contact_ids]


def day_end(now: datetime, tz_name: str) -> datetime:
    local = now.astimezone(ZoneInfo(tz_name or "Europe/Madrid"))
    end = local.replace(hour=23, minute=59, second=59, microsecond=0)
    return end.astimezone(timezone.utc)


def persist_new_signals(supabase, *, company_id: str, user_id: str, signals: list, known: set[str]) -> int:
    """Insert missing keys. Do not resolve older rows from a partial memo window."""
    written = 0
    for signal in signals:
        if signal.dedupe_key in known:
            continue
        supabase.table("action_signals").upsert(
            {
                "company_id": company_id,
                "user_id": user_id,
                "connection_id": signal.connection_id or "",
                "contact_id": signal.contact_id,
                "deal_id": signal.deal_id,
                "memo_id": signal.source_memo_id,
                "type": signal.type,
                "dedupe_key": signal.dedupe_key,
                "payload": {
                    **signal.payload,
                    **({"due_at": signal.due_at.isoformat()} if signal.due_at else {}),
                },
                "status": "pending",
                "coverage": "complete",
            },
            on_conflict="company_id,user_id,connection_id,dedupe_key",
        ).execute()
        known.add(signal.dedupe_key)
        written += 1
    return written


def retracted_objection_ids(existing: list[dict], *, memo_ids: set[str], fresh_keys: set[str]) -> list[str]:
    """A pending objection whose memo was re-read and no longer yields it (C04 found none, or it was resolved)."""
    return _retracted_memo_ids(existing, types={"objection_open"}, memo_ids=memo_ids, fresh_keys=fresh_keys)


def retracted_followup_ids(existing: list[dict], *, memo_ids: set[str], fresh_keys: set[str]) -> list[str]:
    """Lista 4 T2: a pending followup_due whose memo was re-read and no longer yields it - a
    newer conversation, a commitment, or an outcome that closes the contact."""
    return _retracted_memo_ids(existing, types={"followup_due"}, memo_ids=memo_ids, fresh_keys=fresh_keys)


def retracted_handoff_followup_ids(existing: list[dict], *, fresh_keys: set[str]) -> list[str]:
    """Lista 4 T8: a pending handed-off follow-up that no longer applies - the AE's own memo
    took over, the handoff closed, or the date moved. Only called when both reads it
    depends on (handoffs, the SDR's memos) succeeded."""
    return [
        str(row["id"])
        for row in existing
        if row.get("type") == "followup_due"
        and row.get("status") == "pending"
        and str(row.get("dedupe_key") or "").startswith(HANDOFF_FOLLOWUP_KEY_PREFIX)
        and str(row.get("dedupe_key") or "") not in fresh_keys
    ]


def retracted_callback_ids(existing: list[dict], *, memo_ids: set[str], fresh_keys: set[str]) -> list[str]:
    """T5 review (BLOCKING): a pending callback_no_answer whose memo was re-read and no
    longer yields it - a later connected call/memo means it is resolved, the same way a
    resolved objection is."""
    return _retracted_memo_ids(existing, types={"callback_no_answer"}, memo_ids=memo_ids, fresh_keys=fresh_keys)


def _retracted_memo_ids(existing: list[dict], *, types: set[str], memo_ids: set[str], fresh_keys: set[str]) -> list[str]:
    return [
        str(row["id"])
        for row in existing
        if row.get("type") in types
        and row.get("status") == "pending"
        and str(row.get("memo_id") or "") in memo_ids
        and str(row.get("dedupe_key") or "") not in fresh_keys
    ]


def retracted_call_callback_ids(existing: list[dict], *, call_ids: set[str], fresh_keys: set[str]) -> list[str]:
    """T5 review: a pending callback_no_answer built from an outbound_calls row (dedupe key
    `callback:call:{call_id}`) whose call was re-read this window but no longer yields it -
    a newer call or memo already supersedes it."""
    out: list[str] = []
    for row in existing:
        if row.get("type") != "callback_no_answer" or row.get("status") != "pending":
            continue
        key = str(row.get("dedupe_key") or "")
        if not key.startswith("callback:call:"):
            continue
        if key.split(":", 2)[-1] not in call_ids:
            continue
        if key in fresh_keys:
            continue
        out.append(str(row["id"]))
    return out


HOY_MEMO_COLUMNS = (
    "id,hubspot_contact_id,hubspot_deal_id,extraction,capture_started_at,created_at,"
    "company_id,user_id,playbook_version_id,screening_outcome"
)
# Lista 4 (migration 062): only read with HOY_SDR_SECTIONS_ENABLED on.
FOLLOWUP_MEMO_COLUMNS = ",followup_at,rep_outcome"


def read_hoy_memos(supabase, *, company_id: str, user_id: str, with_followup: bool = False) -> list[dict]:
    """The rep's newest memos: the only window Hoy materializes signals from.

    `with_followup` adds memos.followup_at/rep_outcome; before migration 062 that select
    fails, and the memos are read without them (no rep date, no outcome) rather than not
    at all."""
    def read(columns: str) -> list[dict]:
        stored = (
            supabase.table("memos")
            .select(columns)
            .eq("user_id", user_id)
            .or_(f"company_id.eq.{company_id},company_id.is.null")
            .order("created_at", desc=True)
            .limit(HOY_MEMO_LIMIT)
            .execute()
        )
        return list(stored.data or [])

    if with_followup:
        try:
            return read(HOY_MEMO_COLUMNS + FOLLOWUP_MEMO_COLUMNS)
        except Exception:
            pass
    return read(HOY_MEMO_COLUMNS)


def refresh_hoy_signals(
    supabase,
    *,
    company_id: str,
    user_id: str,
    now: datetime,
    tz_name: str,
    lead_tiers_enabled: bool = False,
    callback_after_days: int = DEFAULT_CALLBACK_AFTER_DAYS,
    cadence: dict[str, int] | None = None,
    handoffs: list[dict] | None = None,
    handoff_memos: list[dict] | None = None,
) -> int:
    """`handoffs`/`handoff_memos` (Lista 4 T8, cadence on, AE/General): the active handoffs
    this rep received and the handing-off SDRs' memos about them. None = not read (or the
    read failed): no handed-off follow-up is produced and none stored is retracted."""
    try:
        memos = read_hoy_memos(supabase, company_id=company_id, user_id=user_id, with_followup=cadence is not None)
        existing = (
            supabase.table("action_signals")
            .select("id,dedupe_key,type,status,memo_id")
            .eq("company_id", company_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        return 0
    from app.services.hoy.crm_state import queue_states_enabled

    ignore_deal_closed = queue_states_enabled(supabase, company_id)
    signals = fresh_signals(
        list(stored.data or []),
        now=now,
        day_end=day_end(now, tz_name),
        ignore_deal_closed=ignore_deal_closed,
    )
    known = {str(row.get("dedupe_key") or "") for row in (existing.data or [])}
    fresh_keys = {signal.dedupe_key for signal in signals}
    # With the cadence on, objection_open is no longer produced: its pending rows are hidden
    # on read (GET /today), not resolved, so turning the flag off brings them back untouched.
    retract_memo_rows = retracted_objection_ids if cadence is None else retracted_followup_ids
    retracted = retract_memo_rows(
        list(existing.data or []),
        memo_ids={str(memo.get("id") or "") for memo in memos},
        fresh_keys=fresh_keys,
    )
    retracted += retracted_callback_ids(
        list(existing.data or []),
        memo_ids={str(memo.get("id") or "") for memo in memos},
        fresh_keys=fresh_keys,
    )
    if handoffs_known:
        retracted += retracted_handoff_followup_ids(list(existing.data or []), fresh_keys=fresh_keys)
    retracted += retracted_call_callback_ids(
        list(existing.data or []),
        call_ids={str(call.get("id") or "") for call in calls},
        fresh_keys=fresh_keys,
    )
    if retracted:
        try:
            supabase.table("action_signals").update({"status": "resolved"}).in_("id", retracted).execute()
        except Exception:
            pass
    try:
        return persist_new_signals(
            supabase,
            company_id=company_id,
            user_id=user_id,
            signals=signals,
            known=known,
        )
    except Exception:
        return 0
