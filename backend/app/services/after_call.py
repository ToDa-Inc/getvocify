"""Lista 4 T4 (E10, E11): what happens when the rep hangs up. Pure: no I/O, no clock reads.

After a call the rep confirms the CRM proposal and records one of four outcomes. This module
decides what each outcome means - the call_outcome the CRM sync already understands, whether
the company's rule lets Vocify create a deal for a contact that has none, the follow-up date
the cadence suggests, the contact's lead status to propose, and whether an email was promised.
The effects (store, handoff, resolve Hoy signals, CRM writes) live in app/api/after_call.py.
Everything here is behind AFTER_CALL_FLOW_ENABLED at its call sites.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.services.hoy.cadence import stopper_for, wait_days
from app.services.hoy.signals import touch_from_intelligence

# memos.rep_outcome (migration 062).
MEETING_BOOKED = "meeting_booked"
FOLLOW_UP = "follow_up"
NOT_INTERESTED = "not_interested"
DISQUALIFIED = "disqualified"
REP_OUTCOMES: tuple[str, ...] = (MEETING_BOOKED, FOLLOW_UP, NOT_INTERESTED, DISQUALIFIED)
# Outcomes that close the contact out: the rep must say why (-> lost_reason).
REASON_REQUIRED: frozenset[str] = frozenset({NOT_INTERESTED, DISQUALIFIED})

# crm_configurations.deal_creation_rule (migration 063). "always" is today's behaviour.
DEAL_RULE_ALWAYS = "always"
DEAL_CREATION_RULES: tuple[str, ...] = (DEAL_RULE_ALWAYS, "meeting_booked", "follow_up_or_meeting", "never")
_DEAL_RULE_OUTCOMES: dict[str, frozenset[str]] = {
    "meeting_booked": frozenset({MEETING_BOOKED}),
    "follow_up_or_meeting": frozenset({MEETING_BOOKED, FOLLOW_UP}),
    "never": frozenset(),
}

# A follow-up whose stopper is unknown (no C04 intelligence, or interest "none" the rep still
# wants to chase) comes back in a week - E8's "other" wait.
FALLBACK_FOLLOWUP_DAYS = 7

# HubSpot's own default "Open Deal" lead status - the only value Vocify proposes without the
# account configuring it (see hubspot/call_outcome.py: HS_LEAD_STATUS_CONVERTED).
OPEN_DEAL_LEAD_STATUS = "OPEN_DEAL"

# Commitments the rep made that mean "send an email". C04 kinds "email"/"send" are explicit;
# any other commitment whose text is clearly about sending something by mail also counts.
_EMAIL_KINDS = frozenset({"email", "send"})
_SENDING_TEXT = re.compile(
    r"\b(e-?mail|correo|mail|te (lo |la |los |las )?(env[ií]o|mando)|enviar(te|le|les)?|mandar(te|le|les)?|"
    r"send (you|over|him|her|them)|follow[- ]?up email)\b",
    re.IGNORECASE,
)


def normalize_rule(rule: Optional[str]) -> str:
    """An unknown or missing rule is today's behaviour, never a silent 'never'."""
    return rule if rule in DEAL_CREATION_RULES else DEAL_RULE_ALWAYS


def call_outcome_for(rep_outcome: str) -> str:
    """The rep's outcome as the CRM sync's call_outcome (converted | on_hold | lost)."""
    if rep_outcome == MEETING_BOOKED:
        return "converted"
    if rep_outcome == FOLLOW_UP:
        return "on_hold"
    if rep_outcome in REASON_REQUIRED:
        return "lost"
    raise ValueError(f"unknown rep_outcome: {rep_outcome!r}")


def deal_allowed(rule: Optional[str], rep_outcome: Optional[str]) -> bool:
    """E11: may Vocify create a deal for a contact without one, given this outcome? Without an
    outcome (auto-approve, WhatsApp, an old client) only 'always' creates one."""
    rule = normalize_rule(rule)
    if rule == DEAL_RULE_ALWAYS:
        return True
    return rep_outcome in _DEAL_RULE_OUTCOMES[rule]


def must_skip_deal(rule: Optional[str], rep_outcome: Optional[str], *, has_deal: bool) -> bool:
    """A deal that already exists is always updated; otherwise the rule decides."""
    return not has_deal and not deal_allowed(rule, rep_outcome)


def _as_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _intelligence(memo: dict) -> Optional[dict]:
    extraction = memo.get("extraction") or {}
    intelligence = extraction.get("intelligence") if isinstance(extraction, dict) else None
    return intelligence if isinstance(intelligence, dict) else None


def memo_stopper(memo: dict, now: datetime) -> Optional[str]:
    """Why this call did not end in a meeting (hoy/cadence.stopper_for on the memo's C04)."""
    touch = touch_from_intelligence(
        memo_id=str(memo.get("id") or ""),
        contact_id=None,
        deal_id=None,
        at=_as_dt(memo.get("created_at")) or now,
        intelligence=_intelligence(memo),
    )
    return stopper_for(touch) if touch else None


def suggested_followup_at(memo: dict, company_overrides: Optional[dict[str, int]], now: datetime) -> datetime:
    """E8's date for a follow-up: the call plus its stopper's wait (company overrides first),
    +7 days when the stopper is unknown. Never in the past - reviewing an old call counts from now."""
    at = _as_dt(memo.get("created_at")) or now
    days = wait_days(memo_stopper(memo, now), company_overrides) or FALLBACK_FOLLOWUP_DAYS
    due = at + timedelta(days=days)
    return due if due > now else now + timedelta(days=days)


def proposed_lead_status(rep_outcome: Optional[str], stopper: Optional[str], config: Any) -> Optional[str]:
    """The contact's lead status to propose for this outcome - only values that exist on the
    account: HubSpot's default OPEN_DEAL for a booked meeting, else the account's own mapped
    On hold / Lost values (crm_configurations). Never an invented option (see the docstring of
    hubspot/call_outcome.py for why). None when nothing is configured for that outcome.

    `stopper` does not change the choice today: a timing stopper would suggest BAD_TIMING, but
    that is not a value the account maps, so proposing it could name an option that does not
    exist. It is taken so the call site does not change when per-stopper values are mapped."""
    del stopper
    if rep_outcome == MEETING_BOOKED:
        return OPEN_DEAL_LEAD_STATUS
    if rep_outcome == FOLLOW_UP:
        return getattr(config, "on_hold_lead_status_value", None) or None
    if rep_outcome in REASON_REQUIRED:
        return getattr(config, "lost_lead_status_value", None) or None
    return None


def lead_status_options(config: Any) -> dict[str, Optional[str]]:
    return {
        "on_hold": getattr(config, "on_hold_lead_status_value", None) or None,
        "lost": getattr(config, "lost_lead_status_value", None) or None,
    }


def promised_email(intelligence: Optional[dict]) -> bool:
    """Did the call end with an email owed to the prospect? A C04 email/send commitment the rep
    made, or any commitment whose text is clearly about sending something by mail."""
    for item in (intelligence or {}).get("commitments") or []:
        if not isinstance(item, dict):
            continue
        kind, origin = item.get("kind"), item.get("origin") or "rep_promise"
        if kind in _EMAIL_KINDS and origin == "rep_promise":
            return True
        if kind not in {"call", "meeting"} and _SENDING_TEXT.search(str(item.get("text") or "")):
            return True
    return False


def approval_plan(
    *,
    rep_outcome: str,
    reason: Optional[str],
    lead_status: Optional[str],
    provider: Optional[str],
    rule: Optional[str],
    has_deal: bool,
    config: Any,
) -> dict:
    """What a rep outcome changes in approve_memo_core's sync call.

    - call_outcome/lost_reason: HubSpot only - Pipedrive and Salesforce reject a call_outcome
      (CALL_OUTCOME_UNSUPPORTED), so there the outcome is recorded in Vocify only.
    - skip_deal: the company's deal rule, enforced here and not only in the UI. Not on
      Salesforce, whose sync requires an opportunity (SKIP_DEAL_UNSUPPORTED).
    - the rep's edited lead status replaces the account's mapped On hold / Lost value for this
      write, but only when it is one of those mapped values (never a free-typed option)."""
    provider = (provider or "").lower()
    plan: dict = {"skip_deal": False, "call_outcome": None, "lost_reason": None}
    if provider != "salesforce" and must_skip_deal(rule, rep_outcome, has_deal=has_deal):
        plan["skip_deal"] = True
    if provider != "hubspot":
        return plan
    call_outcome = call_outcome_for(rep_outcome)
    plan["call_outcome"] = call_outcome
    if call_outcome == "lost":
        plan["lost_reason"] = (reason or "").strip() or None
    options = {value for value in lead_status_options(config).values() if value}
    if lead_status and lead_status in options:
        if call_outcome == "lost":
            plan["lost_lead_status_value"] = lead_status
        elif call_outcome == "on_hold":
            plan["on_hold_lead_status_value"] = lead_status
    return plan
