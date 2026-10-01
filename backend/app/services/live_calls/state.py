"""Pure state for the call a rep is on."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Literal, Optional

from app.services.live_calls.crm_url import CrmRecord, Provider

ContactSource = Literal["page", "picked"]
CallStatus = Literal["live", "ended"]


@dataclass(frozen=True)
class LiveCall:
    id: str
    status: CallStatus
    started_at: float
    provider: Optional[Provider] = None
    contact_id: Optional[str] = None
    contact_source: Optional[ContactSource] = None
    # The record on screen when the call started (also a deal or company, where
    # the rep still has to pick the contact).
    record: Optional[CrmRecord] = None
    # The desktop capture memo recording this call, when one was reserved.
    memo_id: Optional[str] = None
    ended_at: Optional[float] = None

    @property
    def is_live(self) -> bool:
        return self.status == "live"

    def to_dict(self) -> dict:
        out = asdict(self)
        out["needs_contact"] = self.contact_id is None
        return out


def start_call(
    call_id: str,
    record: Optional[CrmRecord],
    now: float,
    *,
    connected_account_id: Optional[str] = None,
) -> LiveCall:
    """Open a call with the contact on screen, when that is knowable.

    A contact record from the connected CRM account is the contact. A deal or
    company record is kept so the client can offer its contacts.
    """
    if record is None or not _same_account(record, connected_account_id):
        return LiveCall(id=call_id, status="live", started_at=now)
    is_contact = record.object_type == "contact"
    return LiveCall(
        id=call_id,
        status="live",
        started_at=now,
        provider=record.provider,
        contact_id=record.record_id if is_contact else None,
        contact_source="page" if is_contact else None,
        record=record,
    )


def pick_contact(call: LiveCall, provider: Provider, contact_id: str) -> LiveCall:
    return replace(call, provider=provider, contact_id=contact_id, contact_source="picked")


def attach_memo(call: LiveCall, memo_id: str) -> LiveCall:
    return replace(call, memo_id=memo_id)


def end_call(call: LiveCall, now: float) -> LiveCall:
    if not call.is_live:
        return call
    return replace(call, status="ended", ended_at=now)


def _same_account(record: CrmRecord, connected_account_id: Optional[str]) -> bool:
    if not connected_account_id or not record.account_id:
        # Nothing to compare against: trust the page rather than drop it.
        return True
    return str(record.account_id).lower() == str(connected_account_id).lower()
