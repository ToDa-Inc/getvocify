"""D4/D5 + playbooks v2 T8: which playbook flow a capture lands in, pure and DB-free."""

from __future__ import annotations

from typing import Optional

from app.services.playbooks.catalog import catalog_order, catalog_role, requires_stages

# D5: SDR always prospects, AE always closes. General (or no sales_role) follows the
# channel: a call is prospecting, a meeting or visit is demo/close.
_ROLE_MOTION = {"sdr": "discovery", "ae": "closing"}

# D4: each flow's business objective. Motions outside this map (custom types, qualification)
# have no default goal.
GOAL_FOR_MOTION = {
    "discovery": "meeting_booked",
    "inbound": "meeting_booked",
    "ae_discovery": "demo_booked",
    "closing": "proposal_and_close",
    "negotiation": "close_date",
}


def _role_default(sales_role: Optional[str], interaction_kind: str) -> Optional[str]:
    role = (sales_role or "").strip().lower()
    if role in _ROLE_MOTION:
        return _ROLE_MOTION[role]
    if interaction_kind == "call":
        return "discovery"
    if interaction_kind in ("meeting", "visit"):
        return "closing"
    return None


def rule_matches_static(applies_to: dict, sales_role: Optional[str], interaction_kind: str) -> bool:
    """The rule's role and channel conditions, which are always known at pin time."""
    role = applies_to.get("role") or "any"
    if role != "any" and role != (sales_role or "").strip().lower():
        return False
    channels = applies_to.get("channels") or []
    return not channels or interaction_kind in channels


def rule_matches(applies_to: dict, sales_role: Optional[str], interaction_kind: str, context: Optional[dict]) -> bool:
    """Every non-"any" condition must hold. A condition whose context value is unknown
    (None, or absent) does not hold: an unknown never makes a rule match."""
    if not rule_matches_static(applies_to, sales_role, interaction_kind):
        return False
    context = context or {}
    contact = applies_to.get("contact") or "any"
    if contact in ("new", "contacted") and context.get("contact") != contact:
        return False
    if contact == "inbound" and context.get("inbound") is not True:
        return False
    stages = [str(stage) for stage in (applies_to.get("deal_stages") or [])]
    if stages and str(context.get("deal_stage") or "") not in stages:
        return False
    return True


def specificity(applies_to: dict) -> int:
    """How many conditions the rule sets (role, channels, contact, deal stages)."""
    return sum((
        (applies_to.get("role") or "any") != "any",
        bool(applies_to.get("channels")),
        (applies_to.get("contact") or "any") != "any",
        bool(applies_to.get("deal_stages")),
    ))


def route(
    sales_role: Optional[str],
    interaction_kind: str,
    context: Optional[dict] = None,
    rules: Optional[list[dict]] = None,
) -> tuple[Optional[str], Optional[str]]:
    """(motion, why). why is "rule" for a matching published rule, "role_default" for D5,
    None when nothing has a fixed flow. `rules` is [{key, applies_to, published}]: only
    published ones route; the most specific match wins, ties go to catalog order then key."""
    best_rank: Optional[tuple] = None
    best_key: Optional[str] = None
    for rule in rules or []:
        key = str(rule.get("key") or "")
        applies_to = rule.get("applies_to")
        if not key or not rule.get("published") or not isinstance(applies_to, dict):
            continue
        if requires_stages(key) and not applies_to.get("deal_stages"):
            continue
        if not rule_matches(applies_to, sales_role, interaction_kind, context):
            continue
        rank = (-specificity(applies_to), *catalog_order(key))
        if best_rank is None or rank < best_rank:
            best_rank, best_key = rank, key
    if best_key is not None:
        return best_key, "rule"
    default = _role_default(sales_role, interaction_kind)
    return (default, "role_default") if default else (None, None)


def motion_for(
    sales_role: Optional[str],
    interaction_kind: str,
    context: Optional[dict] = None,
    rules: Optional[list[dict]] = None,
) -> Optional[str]:
    """The sales motion a capture should pin to, from the rep's sales_role and the channel.
    A SDR/AE always gets their flow, whatever the channel. General (or no role) follows the
    channel only for call/meeting/visit; anything else (e.g. voice_note) has no fixed flow,
    so the caller falls back to its existing rule (single published playbook).

    With `rules` (PLAYBOOK_ROUTING_ENABLED) the most specific published rule that matches
    `context` = {contact: "new"|"contacted"|None, inbound: bool|None, deal_stage: str|None}
    goes first; without a match, or without rules, it is the role default above."""
    return route(sales_role, interaction_kind, context, rules)[0]


MOTION_FLOW = {
    "discovery": "sdr",
    "inbound": "sdr",
    "closing": "ae",
    "ae_discovery": "ae",
    "negotiation": "ae",
}


def flow_for_motion(sales_motion_key: Optional[str]) -> Optional[str]:
    """T10: which rep flow a captured motion belongs to, for the post-interaction brief."""
    return MOTION_FLOW.get((sales_motion_key or "").strip())


def goal_for(sales_motion_key: str) -> Optional[str]:
    """The flow's objective, or None when the motion has no fixed goal (D4)."""
    return GOAL_FOR_MOTION.get(sales_motion_key)


def visible_to_role(sales_motion_key: str, sales_role: Optional[str], applies_to: Optional[dict] = None) -> bool:
    """Whether a member with this sales_role should see this motion (D5). A SDR sees SDR
    types and any-role types, an AE the AE ones; general and no role see everything. The
    type's role is its rule's (`applies_to`, when the caller has one), else the catalog's;
    a type with neither (qualification, a legacy custom type) stays visible."""
    role = (sales_role or "").strip().lower()
    if role not in ("sdr", "ae"):
        return True
    type_role = (applies_to or {}).get("role") if isinstance(applies_to, dict) else None
    type_role = type_role or catalog_role(sales_motion_key)
    if type_role in (None, "any"):
        return True
    return type_role == role
