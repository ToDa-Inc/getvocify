"""Hoy engine. Pure rules over a contact's captured interactions: no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Optional

from app.services.hoy.cadence import followup_due_at, stopper_for

Interest = Literal["high", "medium", "low", "none"]
SignalType = Literal[
    "commitment_due",
    "no_reply",
    "going_cold",
    "objection_open",
    "confirm_pending",
    "meeting_today",
    "callback_no_answer",
    "never_contacted",
    "followup_due",
]
CommitmentKind = Literal["call", "email", "send", "meeting", "other"]
ScreeningOutcome = Literal["connected", "voicemail", "no_response"]

COLD_AFTER = timedelta(days=10)
WARM: frozenset[str] = frozenset({"high", "medium"})
# T5 (D HOY_LEAD_TIERS_ENABLED): callback_no_answer joins no_reply at tier 1; never_contacted
# is the lowest tier - it is not a conversation gone quiet, it is one that never started.
# going_cold keeps its tier and its persisted type; only its reason() wording changes ("stale_hot").
TIER: dict[str, int] = {
    "commitment_due": 0,
    "meeting_today": 0,
    "callback_no_answer": 1,
    "no_reply": 1,
    "going_cold": 2,
    # Lista 4 T2 (HOY_SDR_SECTIONS_ENABLED): replaces going_cold and objection_open for a
    # SDR/General rep, on the date the stopper's cadence sets (hoy/cadence.py).
    "followup_due": 2,
    "objection_open": 3,
    "never_contacted": 4,
}
DEFAULT_LIMIT = 7
# Last attempt outcomes (telephony/call_screening.resolve_screening_outcome) that count as
# "no answer" for a callback_no_answer card - a real conversation never happened after them.
UNANSWERED_OUTCOMES: frozenset[str] = frozenset({"no_response", "voicemail", "bad_moment", "cut_off"})
# C04 v8 call types that mean the same thing when telephony screening did not say it: nobody
# picked up for real, or they could not talk and the call ended at once.
_UNANSWERED_CALL_TYPES = {"no_conversation": "no_response", "bad_moment": "bad_moment"}


def _with_v8_callback(commitments: tuple, intelligence: dict) -> tuple:
    """C04 v8 `next.callback`: the agreed callback, with its reason, is the call commitment Hoy,
    the brief and the CRM task all read. It completes a dated call commitment that lacks a reason,
    or becomes one when C04 listed none."""
    nxt = intelligence.get("next") if isinstance(intelligence.get("next"), dict) else {}
    callback = nxt.get("callback") if isinstance(nxt.get("callback"), dict) else {}
    if not callback.get("needed"):
        return commitments
    why = " ".join(str(callback.get("reason") or "").split()) or None
    origin = "prospect_request" if callback.get("who_asked") == "prospect" else "rep_promise"
    calls = [c for c in commitments if c.kind == "call"]
    if calls:
        return tuple(
            Commitment(kind=c.kind, origin=c.origin, text=c.text, due_at=c.due_at, why=c.why or why)
            if c.kind == "call" else c
            for c in commitments
        )
    raw = callback.get("when")
    try:
        due = datetime.fromisoformat(str(raw).replace("Z", "+00:00")) if raw else None
    except ValueError:
        due = None
    if due is None or due.tzinfo is None:
        return commitments
    return commitments + (Commitment(kind="call", origin=origin, text="volver a llamar", due_at=due, why=why),)


def screening_from_call(screening_outcome: Optional[str], intelligence: Optional[dict]) -> Optional[str]:
    """The telephony outcome when it says the call went unanswered; otherwise what the call
    reading saw (a "connected" call can still be a voicemail or a "me pillas fatal")."""
    if screening_outcome in UNANSWERED_OUTCOMES:
        return screening_outcome
    call = (intelligence or {}).get("call") if isinstance(intelligence, dict) else None
    derived = _UNANSWERED_CALL_TYPES.get((call or {}).get("call_type")) if isinstance(call, dict) else None
    if not derived and isinstance(call, dict) and call.get("ended_abruptly") is True:
        derived = "cut_off"  # the line dropped mid-conversation: nothing was closed
    return derived or screening_outcome


@dataclass(frozen=True)
class Commitment:
    kind: CommitmentKind
    origin: Literal["prospect_request", "rep_promise"]
    text: str
    due_at: datetime
    # C04 v8: why this call is owed, in the call's terms ("estaba recogiendo a los niños").
    why: Optional[str] = None


@dataclass(frozen=True)
class Touch:
    """One captured interaction (a memo), as the engine sees it."""

    memo_id: str
    contact_id: Optional[str]
    deal_id: Optional[str]
    at: datetime
    interest: Optional[Interest] = None
    objections: tuple[tuple[str, str], ...] = ()
    commitments: tuple[Commitment, ...] = ()
    deal_closed: bool = False
    connection_id: Optional[str] = None
    screening_outcome: Optional[ScreeningOutcome] = None
    # Lista 4 (migration 062, written by T4 after the call): the date the rep picked to come
    # back, and the outcome they recorded. None when unknown or not yet written.
    followup_at: Optional[datetime] = None
    rep_outcome: Optional[str] = None


@dataclass(frozen=True)
class Signal:
    type: SignalType
    contact_id: Optional[str]
    deal_id: Optional[str]
    source_memo_id: str
    due_at: Optional[datetime]
    payload: dict = field(compare=False)
    dedupe_key: str = ""
    connection_id: Optional[str] = None


@dataclass(frozen=True)
class Card:
    primary: Signal
    supporting: tuple[Signal, ...] = ()


def signals_for_contact(
    touches: list[Touch],
    *,
    now: datetime,
    day_end: datetime,
    callback_after_days: Optional[int] = None,
    cadence: Optional[dict[str, int]] = None,
) -> list[Signal]:
    """All touches for ONE contact, any order. `day_end` is the end of the rep's local day.

    `callback_after_days` is None unless HOY_LEAD_TIERS_ENABLED is on for a SDR/General rep
    (T5): with it None, no callback_no_answer is ever produced, so the flag off behaves
    exactly as before.

    `cadence` is None unless HOY_SDR_SECTIONS_ENABLED is on for a SDR/General rep (Lista 4
    T2); otherwise it is the company's overrides ({} = E8 defaults). With it, going_cold and
    objection_open give way to one followup_due that only exists from its due day on."""
    if not touches:
        return []
    last = max(touches, key=lambda t: t.at)
    if last.deal_closed:
        return []

    base = {
        "contact_id": last.contact_id,
        "deal_id": last.deal_id,
        "source_memo_id": last.memo_id,
        "connection_id": last.connection_id,
    }
    out: list[Signal] = []

    for commitment in last.commitments:
        if commitment.due_at <= day_end:
            out.append(Signal(
                "commitment_due",
                due_at=commitment.due_at,
                payload={
                    "kind": commitment.kind, "origin": commitment.origin, "text": commitment.text,
                    **({"why": commitment.why} if commitment.why else {}),
                },
                dedupe_key=commitment_key(last.memo_id, commitment.kind, commitment.due_at),
                **base,
            ))

    if (
        callback_after_days is not None
        and not out
        and last.screening_outcome in UNANSWERED_OUTCOMES
        and now - last.at >= timedelta(days=callback_after_days)
    ):
        out.append(Signal(
            "callback_no_answer",
            due_at=None,
            # `at`, not a precomputed day count (review): the card's day count is read off
            # this timestamp at render time, so it never goes stale between refreshes.
            payload={"outcome": last.screening_outcome, "at": last.at.isoformat()},
            dedupe_key=f"callback:{last.memo_id}",
            **base,
        ))

    waiting_on_future = any(commitment.due_at > day_end for commitment in last.commitments)
    if cadence is not None:
        if not out and not waiting_on_future:
            followup = _followup_due(last, now=now, day_end=day_end, overrides=cadence, base=base)
            if followup is not None:
                out.append(followup)
        return out

    if last.interest in WARM and now - last.at >= COLD_AFTER and not out and not waiting_on_future:
        out.append(Signal(
            "going_cold",
            due_at=None,
            payload={"interest": last.interest, "days_silent": (now - last.at).days},
            dedupe_key=f"cold:{last.memo_id}",
            **base,
        ))

    if last.objections and last.interest in (WARM | {"low"}):
        category, quote = last.objections[-1]
        out.append(Signal(
            "objection_open",
            due_at=None,
            payload={"category": category, "quote": quote, "touch_at": last.at.isoformat()},
            dedupe_key=f"objection:{last.memo_id}:{category}",
            **base,
        ))
    return out


def _followup_due(last: Touch, *, now: datetime, day_end: datetime, overrides: dict, base: dict) -> Optional[Signal]:
    """Nothing before its due day (the rep's local day, like a commitment): a contact called
    yesterday is not called again today to say the same thing."""
    due = followup_due_at(last, overrides)
    if due is None or due > day_end:
        return None
    payload = {
        "stopper": stopper_for(last),
        "interest": last.interest,
        "days_since": (now - last.at).days,
        # The card's day count is read off this at render time (reasons.py), like callbacks.
        "touch_at": last.at.isoformat(),
        "due_at": due.isoformat(),
    }
    if last.objections:
        category, quote = last.objections[-1]
        payload.update({"category": category, "quote": quote})
    return Signal(
        "followup_due",
        due_at=due,
        payload=payload,
        # Stable per memo and due day: a dismissed or snoozed follow-up is never resurrected
        # by reconcile, but a new date the rep picks later (memos.followup_at) is a new key.
        dedupe_key=f"followup:{last.memo_id}:{due.date().isoformat()}",
        **base,
    )


def never_contacted_signal(
    *, contact_id: str, connection_id: Optional[str], deal_id: Optional[str] = None,
    contact_name: Optional[str] = None,
) -> Signal:
    """T5: an assigned contact with no calls and no memos, full coverage. Not touch-based -
    there is no last Touch, so this is built directly rather than via signals_for_contact.
    `contact_name` comes from the CRM read: with no memo there is no other place to name it."""
    return Signal(
        "never_contacted",
        contact_id=contact_id,
        deal_id=deal_id,
        source_memo_id="",
        due_at=None,
        payload={"contact_name": contact_name} if contact_name else {},
        dedupe_key=f"never_contacted:{connection_id or ''}:{contact_id}",
        connection_id=connection_id,
    )


def commitment_key(memo_id: str, kind: str, due_at: datetime) -> str:
    return f"commitment:{memo_id}:{kind}:{due_at.date().isoformat()}"


def commitment_task_links(memos: list[dict]) -> dict[str, list[str]]:
    """Signal key -> CRM task ids written for that commitment (extraction.intelligence.commitments[].crm_task_id)."""
    links: dict[str, list[str]] = {}
    for memo in memos:
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
        for item in intelligence.get("commitments") or []:
            if not isinstance(item, dict) or not item.get("crm_task_id") or not isinstance(item.get("due_at"), str):
                continue
            try:
                due = datetime.fromisoformat(item["due_at"].replace("Z", "+00:00"))
            except ValueError:
                continue
            key = commitment_key(str(memo.get("id") or ""), item.get("kind") or "other", due)
            links.setdefault(key, []).append(str(item["crm_task_id"]))
    return links


def _rank_key(signal: Signal, now: datetime) -> tuple:
    """`heat` (T5, hoy/heat.py) is the second criterion within a tier: hotter first. It is
    0 unless the caller attached it, so with HOY_LEAD_TIERS_ENABLED off every card ties on
    it and ordering is exactly what it was before."""
    tier = TIER[signal.type]
    heat = int(signal.payload.get("heat") or 0)
    if signal.type == "commitment_due":
        if signal.due_at is None:
            sub = (1, float("inf"))
        else:
            sub = (0 if signal.due_at < now else 1, signal.due_at.timestamp())
    elif signal.type == "meeting_today":
        due = signal.due_at.timestamp() if signal.due_at else float("inf")
        sub = (0, due)
    elif signal.type == "no_reply":
        sub = (0, datetime.fromisoformat(str(signal.payload["email_at"]).replace("Z", "+00:00")).timestamp())
    elif signal.type == "callback_no_answer":
        raw_at = signal.payload.get("at")
        sub = (0, datetime.fromisoformat(str(raw_at).replace("Z", "+00:00")).timestamp() if raw_at else 0.0)
    elif signal.type == "going_cold":
        sub = (0 if signal.payload["interest"] == "high" else 1, signal.payload["days_silent"])
    elif signal.type == "never_contacted":
        sub = (0, 0)
    elif signal.type == "followup_due":
        raw_due = signal.payload.get("due_at")
        due = datetime.fromisoformat(str(raw_due).replace("Z", "+00:00")).timestamp() if raw_due else 0.0
        sub = (0 if signal.payload.get("interest") == "high" else 1, due)
    else:
        sub = (0, -datetime.fromisoformat(signal.payload["touch_at"]).timestamp())
    return (tier, -heat, *sub)


def rank_cards(signals: list[Signal], *, now: datetime, limit: int = DEFAULT_LIMIT) -> tuple[list[Card], int]:
    """One card per contact. Returns (visible cards, how many more are folded).

    A stored signal of a type this build does not rank (an older release wrote it) is left out: one stale row must
    not take the whole page down."""
    groups: dict[str, list[Signal]] = {}
    for signal in signals:
        if signal.type not in TIER:
            continue
        groups.setdefault(signal.contact_id or signal.deal_id or signal.source_memo_id, []).append(signal)
    cards: list[Card] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda item: _rank_key(item, now))
        cards.append(Card(primary=ordered[0], supporting=tuple(ordered[1:])))
    cards.sort(key=lambda card: _rank_key(card.primary, now))
    return cards[:limit], max(0, len(cards) - limit)


def reconcile(known: dict[str, str], fresh: list[Signal]) -> tuple[list[Signal], set[str]]:
    """Never resurrects a key the rep already acted on. Resolves pending keys that stopped applying."""
    fresh_keys = {signal.dedupe_key for signal in fresh}
    to_insert = [signal for signal in fresh if signal.dedupe_key not in known]
    to_resolve = {key for key, status in known.items() if status == "pending" and key not in fresh_keys}
    return to_insert, to_resolve


def touch_from_intelligence(
    *,
    memo_id: str,
    contact_id: Optional[str],
    deal_id: Optional[str],
    at: Optional[datetime],
    connection_id: Optional[str] = None,
    intelligence: Optional[dict] = None,
    history_complete: bool = True,
    legacy_objections: Optional[str] = None,
    screening_outcome: Optional[str] = None,
    followup_at: Optional[datetime] = None,
    rep_outcome: Optional[str] = None,
) -> Optional[Touch]:
    """Unknown interest stays unknown. A resolved objection is not open, even if legacy text exists."""
    if at is None or (not history_complete and not intelligence):
        return None
    interest = None
    objections: tuple[tuple[str, str], ...] = ()
    commitments: tuple[Commitment, ...] = ()
    deal_closed = False
    if intelligence:
        raw_interest = intelligence.get("interest")
        if raw_interest in {"high", "medium", "low", "none"}:
            interest = raw_interest
        for objection in intelligence.get("objections") or []:
            if objection.get("state") != "open":
                continue
            objections += ((objection.get("category") or "other", objection.get("quote") or ""),)
        for item in intelligence.get("commitments") or []:
            due = item.get("due_at")
            if isinstance(due, str):
                due = datetime.fromisoformat(due.replace("Z", "+00:00"))
            if not isinstance(due, datetime):
                continue
            commitments += (Commitment(
                kind=item.get("kind") or "other",
                origin=item.get("origin") or "rep_promise",
                text=item.get("text") or "",
                due_at=due,
            ),)
        commitments = _with_v8_callback(commitments, intelligence)
        deal_closed = intelligence.get("deal_closed") is True
    elif legacy_objections and history_complete:
        objections = (("other", legacy_objections),)
    return Touch(
        memo_id=memo_id,
        contact_id=contact_id,
        deal_id=deal_id,
        at=at,
        interest=interest,
        objections=objections,
        commitments=commitments,
        deal_closed=deal_closed,
        connection_id=connection_id,
        screening_outcome=screening_outcome if screening_outcome in UNANSWERED_OUTCOMES | {"connected"} else None,
        followup_at=followup_at,
        rep_outcome=rep_outcome,
    )
