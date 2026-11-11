"""Which deal preview should lock: what the rep asked for, else the contact's only open deal."""

from __future__ import annotations

from typing import Optional, Tuple


def unique_associated_contact_id(contacts: list) -> Optional[str]:
    """Lock a contact only when the record has exactly one association."""
    if not isinstance(contacts, list) or len(contacts) != 1:
        return None
    cid = contacts[0].get("contact_id") if isinstance(contacts[0], dict) else None
    return str(cid) if cid else None


def resolve_preview_deal_selection(
    *,
    deal_id: Optional[str],
    create_new_deal: bool,
    has_selected_contact: bool,
    has_contact_candidates: bool,
    linked_deal_count: int = 0,
    skip_deal: bool = False,
    linked_open_deal_ids: Optional[list[str]] = None,
) -> Tuple[Optional[str], bool]:
    """
    Return (selected_deal_id, create_new).

    A contact with exactly one open deal lands on that deal by default; with none or several,
    the rep picks (contact only until then). linked_deal_count is kept for older callers.
    """
    del linked_deal_count
    if skip_deal:
        return None, False
    if deal_id:
        return deal_id, False
    if create_new_deal:
        return None, True
    open_ids = [d for d in (linked_open_deal_ids or []) if d]
    if has_selected_contact and len(open_ids) == 1:
        return open_ids[0], False
    if has_selected_contact or has_contact_candidates:
        return None, False
    return None, True


def open_linked_deal_ids(anchor) -> list[str]:
    """The contact's linked deals known to be open (a deal whose state is unknown is not counted)."""
    return [str(d.deal_id) for d in (getattr(anchor, "deal_matches", None) or []) if getattr(d, "is_open", None) is True]
