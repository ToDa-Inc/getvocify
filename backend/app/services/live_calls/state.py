"""Pure state: the CRM record a rep has open, and the call they are on."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Literal, Optional

Provider = Literal["hubspot", "pipedrive"]
ObjectType = Literal["contact", "company", "deal"]
ContactSource = Literal["page", "picked"]
CallStatus = Literal["live", "ended"]

# A record seen this recently is where the rep clicked Call. Older than this it
# is only offered as a suggestion.
PRESENCE_ASSIGN_SECONDS = 30 * 60


@dataclass(frozen=True)
class RecordPresence:
    """Where the rep last was in the CRM (reported by the extension).

    object_type/record_id are None on a CRM page that is not a record (a list,
    a sequence, the inbox): a call started from there has no known contact.
    """

    provider: Provider
    object_type: Optional[ObjectType]
    record_id: Optional[str]
    account_id: Optional[str]
    seen_at: float

    @property
    def on_record(self) -> bool:
        return bool(self.object_type and self.record_id)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LiveCall:
    id: str
    status: CallStatus
    started_at: float
    provider: Optional[Provider] = None
    contact_id: Optional[str] = None
    contact_source: Optional[ContactSource] = None
    # The record the call was started from (also when it is a deal or company,
    # where the rep still has to pick the contact).
    record: Optional[RecordPresence] = None
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


def presence_is_fresh(presence: Optional[RecordPresence], now: float) -> bool:
    return presence is not None and now - presence.seen_at <= PRESENCE_ASSIGN_SECONDS


def start_call(
    call_id: str,
    presence: Optional[RecordPresence],
    now: float,
    *,
    connected_account_id: Optional[str] = None,
) -> LiveCall:
    """Open a call with the contact the rep had on screen, when that is knowable.

    Only a fresh contact record from the connected CRM account is assigned. A
    deal or company record is kept so the client can offer its contacts.
    """
    usable = (
        presence_is_fresh(presence, now)
        and presence is not None
        and presence.on_record
        and _same_account(presence, connected_account_id)
    )
    if not usable:
        return LiveCall(id=call_id, status="live", started_at=now)
    assert presence is not None
    is_contact = presence.object_type == "contact"
    return LiveCall(
        id=call_id,
        status="live",
        started_at=now,
        provider=presence.provider,
        contact_id=presence.record_id if is_contact else None,
        contact_source="page" if is_contact else None,
        record=presence,
    )


def pick_contact(call: LiveCall, provider: Provider, contact_id: str) -> LiveCall:
    return replace(call, provider=provider, contact_id=contact_id, contact_source="picked")


def attach_memo(call: LiveCall, memo_id: str) -> LiveCall:
    return replace(call, memo_id=memo_id)


def end_call(call: LiveCall, now: float) -> LiveCall:
    if not call.is_live:
        return call
    return replace(call, status="ended", ended_at=now)


def _same_account(presence: Optional[RecordPresence], connected_account_id: Optional[str]) -> bool:
    if presence is None:
        return False
    if not connected_account_id or not presence.account_id:
        # Nothing to compare against: trust the record rather than drop it.
        return True
    return str(presence.account_id) == str(connected_account_id)
