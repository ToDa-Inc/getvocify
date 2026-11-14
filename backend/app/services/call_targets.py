"""Which CRM records a call is saved on (crm_configurations.call_targets, migration 090).

A company that works by deal, by organization or by contact chooses any of the three; the call's note, its call
activity and its tasks go on the chosen records it has. A call with none of them goes on whichever it has, so a
note is never lost to the setting.
"""
from typing import Any, Iterable, Optional

ALL: tuple[str, ...] = ("deal", "company", "contact")


def targets_for(config: Any = None, override: Optional[Iterable[str]] = None) -> frozenset[str]:
    """The rep's choice for this call, else the company's setting, else all three (before migration 090)."""
    for source in (override, getattr(config, "call_targets", None) if config is not None else None):
        chosen = frozenset(t for t in (source or ()) if t in ALL)
        if chosen:
            return chosen
    return frozenset(ALL)


def pick(
    targets: Iterable[str],
    *,
    deal_id: Optional[str],
    contact_id: Optional[str],
    company_id: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(deal_id, contact_id, company_id) the call is linked to: the chosen ones it has, else every one it has."""
    have = {"deal": deal_id, "contact": contact_id, "company": company_id}
    chosen = {key: value for key, value in have.items() if value and key in set(targets)}
    if not chosen:
        chosen = {key: value for key, value in have.items() if value}
    return chosen.get("deal"), chosen.get("contact"), chosen.get("company")
