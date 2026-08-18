"""Which deal preview should lock — never invent one from linked deals."""

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
) -> Tuple[Optional[str], bool]:
    """
    Return (selected_deal_id, create_new).

    linked_deal_count is accepted so callers can pass identity.deal_matches
    length, but a single linked deal is not auto-selected.
    """
    del linked_deal_count
    if deal_id:
        return deal_id, False
    if create_new_deal:
        return None, True
    if has_selected_contact or has_contact_candidates:
        return None, False
    return None, True
