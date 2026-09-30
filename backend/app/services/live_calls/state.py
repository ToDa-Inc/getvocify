"""Pure state for one live call: events in, snapshot out. No I/O here."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Literal, Optional

EventKind = Literal["started", "answered", "ended", "completed"]
Direction = Literal["outbound", "inbound"]
ContactSource = Literal["page", "phone"]
CallStatus = Literal["dialing", "connected", "ended", "completed"]

_STATUS_FOR_EVENT: dict[str, CallStatus] = {
    "started": "dialing",
    "answered": "connected",
    "ended": "ended",
    "completed": "completed",
}


@dataclass(frozen=True)
class LiveCallEvent:
    """One dialer event as observed on the CRM page."""

    provider: str
    source: str
    event: EventKind
    external_call_id: str
    occurred_at: float
    direction: Direction = "outbound"
    to_number: Optional[str] = None
    from_number: Optional[str] = None
    end_status: Optional[str] = None
    engagement_id: Optional[str] = None
    page_object_type: Optional[str] = None
    page_record_id: Optional[str] = None


@dataclass(frozen=True)
class LiveCall:
    """What the rep's clients need to know about the call in progress."""

    external_call_id: str
    provider: str
    source: str
    status: CallStatus
    direction: Direction
    remote_number: Optional[str]
    started_at: float
    updated_at: float
    contact_id: Optional[str] = None
    contact_name: Optional[str] = None
    contact_source: Optional[ContactSource] = None
    page_object_type: Optional[str] = None
    page_record_id: Optional[str] = None
    answered_at: Optional[float] = None
    ended_at: Optional[float] = None
    end_status: Optional[str] = None
    engagement_id: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self.status in ("dialing", "connected")

    def to_dict(self) -> dict:
        return asdict(self)


def remote_number(event: LiveCallEvent) -> Optional[str]:
    """The other party's number: dialed for outbound, caller for inbound."""
    raw = event.from_number if event.direction == "inbound" else event.to_number
    value = (raw or "").strip()
    return value or None


def contact_from_page(event: LiveCallEvent) -> Optional[str]:
    """The open record is the contact only when the rep is on a contact page."""
    if event.page_object_type != "contact":
        return None
    record_id = (event.page_record_id or "").strip()
    return record_id or None


def apply_event(current: Optional[LiveCall], event: LiveCallEvent) -> LiveCall:
    """Fold one event into the call it belongs to.

    A different external_call_id starts a new call. Later events without a
    prior "started" (the extension loaded mid-call) still produce a call so
    clients learn it exists.
    """
    same_call = current is not None and current.external_call_id == event.external_call_id
    status = _STATUS_FOR_EVENT[event.event]

    if not same_call:
        page_contact = contact_from_page(event)
        return LiveCall(
            external_call_id=event.external_call_id,
            provider=event.provider,
            source=event.source,
            status=status,
            direction=event.direction,
            remote_number=remote_number(event),
            started_at=event.occurred_at,
            updated_at=event.occurred_at,
            contact_id=page_contact,
            contact_source="page" if page_contact else None,
            page_object_type=event.page_object_type,
            page_record_id=event.page_record_id,
            answered_at=event.occurred_at if event.event == "answered" else None,
            ended_at=event.occurred_at if event.event in ("ended", "completed") else None,
            end_status=event.end_status,
            engagement_id=event.engagement_id,
        )

    assert current is not None
    if _rank(status) < _rank(current.status):
        status = current.status
    # Events can arrive out of order; a late "started" still carries the
    # record and number the call was opened with.
    page_contact = None if current.contact_id else contact_from_page(event)
    return replace(
        current,
        status=status,
        updated_at=event.occurred_at,
        contact_id=current.contact_id or page_contact,
        contact_source=current.contact_source or ("page" if page_contact else None),
        page_object_type=current.page_object_type or event.page_object_type,
        page_record_id=current.page_record_id or event.page_record_id,
        remote_number=current.remote_number or remote_number(event),
        answered_at=current.answered_at
        or (event.occurred_at if event.event == "answered" else None),
        ended_at=current.ended_at
        or (event.occurred_at if event.event in ("ended", "completed") else None),
        end_status=event.end_status or current.end_status,
        engagement_id=event.engagement_id or current.engagement_id,
    )


def with_contact(
    call: LiveCall,
    contact_id: str,
    *,
    source: ContactSource,
    name: Optional[str] = None,
    now: float,
) -> LiveCall:
    return replace(
        call,
        contact_id=contact_id,
        contact_name=name or call.contact_name,
        contact_source=source,
        updated_at=now,
    )


def _rank(status: CallStatus) -> int:
    return ("dialing", "connected", "ended", "completed").index(status)
