"""Hoy engine. Pure rules over a contact's captured interactions: no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Optional

Interest = Literal["high", "medium", "low", "none"]
SignalType = Literal["commitment_due", "no_reply", "going_cold", "objection_open"]
CommitmentKind = Literal["call", "email", "send", "meeting", "other"]

COLD_AFTER = timedelta(days=10)
WARM: frozenset[str] = frozenset({"high", "medium"})
TIER: dict[str, int] = {"commitment_due": 0, "no_reply": 1, "going_cold": 2, "objection_open": 3}
DEFAULT_LIMIT = 7


@dataclass(frozen=True)
class Commitment:
    kind: CommitmentKind
    origin: Literal["prospect_request", "rep_promise"]
    text: str
    due_at: datetime


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


def signals_for_contact(touches: list[Touch], *, now: datetime, day_end: datetime) -> list[Signal]:
    """All touches for ONE contact, any order. `day_end` is the end of the rep's local day."""
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
                payload={"kind": commitment.kind, "origin": commitment.origin, "text": commitment.text},
                dedupe_key=f"commitment:{last.memo_id}:{commitment.kind}:{commitment.due_at.date().isoformat()}",
                **base,
            ))

    waiting_on_future = any(commitment.due_at > day_end for commitment in last.commitments)
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


def _rank_key(signal: Signal, now: datetime) -> tuple:
    tier = TIER[signal.type]
    if signal.type == "commitment_due":
        if signal.due_at is None:
            return (tier, 1, float("inf"))
        return (tier, 0 if signal.due_at < now else 1, signal.due_at.timestamp())
    if signal.type == "no_reply":
        return (tier, 0, datetime.fromisoformat(str(signal.payload["email_at"]).replace("Z", "+00:00")).timestamp())
    if signal.type == "going_cold":
        return (tier, 0 if signal.payload["interest"] == "high" else 1, signal.payload["days_silent"])
    return (tier, 0, -datetime.fromisoformat(signal.payload["touch_at"]).timestamp())


def rank_cards(signals: list[Signal], *, now: datetime, limit: int = DEFAULT_LIMIT) -> tuple[list[Card], int]:
    """One card per contact. Returns (visible cards, how many more are folded)."""
    groups: dict[str, list[Signal]] = {}
    for signal in signals:
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
    )
