"""Playbooks v2 T8: the rules a company routes calls with, the context they are matched
against, and the re-pin that runs just before C04.

`motion.route` is the pure decision. Everything here is best-effort I/O around it: any
failure means "context unknown", and an unknown never matches a rule, so a capture is
never blocked and falls back to the role default (D5) exactly as it did before routing.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.playbooks.catalog import (
    CATALOG_KEYS,
    catalog_order,
    catalog_role,
    effective_applies_to,
    is_catalog,
    requires_stages,
)
from app.services.playbooks.motion import goal_for, route, rule_matches_static

logger = logging.getLogger(__name__)

ROUTING_FLAG = "PLAYBOOK_ROUTING_ENABLED"
SALES_ROLES_FLAG = "SALES_ROLES_ENABLED"
PIN_META_KEY = "playbook_pin"
CRM_TIMEOUT = 3.0

# HubSpot's "original source" for a contact that came in on its own (a tracked visit, a
# form, an email or a campaign). OFFLINE is a contact somebody created or imported.
_HUBSPOT_INBOUND_SOURCES = frozenset({
    "ORGANIC_SEARCH", "PAID_SEARCH", "EMAIL_MARKETING", "SOCIAL_MEDIA", "REFERRALS",
    "OTHER_CAMPAIGNS", "DIRECT_TRAFFIC", "PAID_SOCIAL",
})


def routing_enabled(supabase: Any, company_id: Optional[str]) -> bool:
    from app.services.feature_flags import is_enabled

    return bool(company_id) and is_enabled(supabase, company_id, ROUTING_FLAG)


def rules_from(motions: dict, details: dict) -> list[dict]:
    """[{key, applies_to, published}] in catalog order. A type with no valid rule of its own
    and no catalog default (qualification, a legacy custom type) is never routed to."""
    keys = set(motions) | set(details) | set(CATALOG_KEYS)
    out: list[dict] = []
    for key in sorted(keys, key=catalog_order):
        applies_to = effective_applies_to(key, (details.get(key) or {}).get("applies_to"))
        if applies_to is None:
            continue
        out.append({"key": key, "applies_to": applies_to, "published": motions.get(key) == "published"})
    return out


def build_details(keys, stored: dict) -> dict:
    """GET /playbooks `details`: per type its label, role, effective rule, goal and whether
    it is a catalog type. `stored` is store.details(company_id)."""
    out: dict = {}
    for key in keys:
        meta = stored.get(key) or {}
        applies_to = effective_applies_to(key, meta.get("applies_to"))
        out[key] = {
            "label": meta.get("label") or None,
            "role": (applies_to or {}).get("role") or catalog_role(key),
            "applies_to": applies_to,
            "goal": goal_for(key),
            "catalog": is_catalog(key),
        }
    return out


def load_rules(supabase: Any, company_id: str) -> list[dict]:
    from app.services.playbooks.store import SupabasePlaybookStore

    store = SupabasePlaybookStore(supabase)
    return rules_from(store.motions(company_id), store.details(company_id))


def _needs(rules: list[dict], sales_role: Optional[str], interaction_kind: str) -> dict[str, bool]:
    """Which context signals could change the outcome, so the CRM is only asked when a
    published rule for this role and channel actually depends on it."""
    need = {"contact": False, "inbound": False, "stage": False}
    for rule in rules:
        applies_to = rule.get("applies_to") or {}
        if not rule.get("published") or not rule_matches_static(applies_to, sales_role, interaction_kind):
            continue
        if requires_stages(rule.get("key")) and not applies_to.get("deal_stages"):
            continue
        contact = applies_to.get("contact") or "any"
        need["contact"] |= contact in ("new", "contacted")
        need["inbound"] |= contact == "inbound"
        need["stage"] |= bool(applies_to.get("deal_stages"))
    return need


def _prior_memo(supabase: Any, company_id: str, column: str, value: str, exclude_memo_id: Optional[str]) -> bool:
    query = (
        supabase.table("memos")
        .select("id")
        .eq("company_id", company_id)
        .eq(column, value)
        .neq("status", "failed")
    )
    if exclude_memo_id:
        query = query.neq("id", exclude_memo_id)
    return bool(getattr(query.limit(1).execute(), "data", None))


def contact_status(
    supabase: Any,
    company_id: str,
    *,
    contact_id: Optional[str],
    deal_id: Optional[str],
    exclude_memo_id: Optional[str] = None,
) -> Optional[str]:
    """"contacted" when an earlier memo of the company is about this contact or deal (the
    same signal Hoy uses for never_contacted), "new" when there is none, None when the
    capture names neither so nothing can be said."""
    checks = [(column, str(value)) for column, value in (("hubspot_contact_id", contact_id), ("hubspot_deal_id", deal_id)) if value]
    if not checks:
        return None
    try:
        for column, value in checks:
            if _prior_memo(supabase, company_id, column, value, exclude_memo_id):
                return "contacted"
    except Exception:
        logger.warning("playbook routing: prior memo lookup failed", exc_info=True)
        return None
    return "new"


def crm_connection(supabase: Any, company_id: str) -> Optional[dict]:
    """The company's connected HubSpot (else Pipedrive) connection, None when there is none."""
    for provider in ("hubspot", "pipedrive"):
        rows = (
            supabase.table("crm_connections")
            .select("*")
            .eq("company_id", company_id)
            .eq("provider", provider)
            .eq("status", "connected")
            .limit(1)
            .execute()
        ).data or []
        if rows:
            return rows[0]
    return None


def _fetch(connection: dict):
    import httpx

    from app.api.today import _http_task_page

    def fetch(request: dict) -> dict:
        with httpx.Client(timeout=CRM_TIMEOUT) as client:
            return _http_task_page(connection, request, client=client)

    return fetch


def deal_stage_for(connection: dict, deal_id: str) -> Optional[str]:
    """The deal's current CRM stage id, None when it cannot be read."""
    provider = str(connection.get("provider") or "")
    fetch = _fetch(connection)
    if provider == "hubspot":
        from app.services.hoy.deals import deal_stages_by_provider

        stage = deal_stages_by_provider(fetch, "hubspot", [deal_id]).get(str(deal_id)) or {}
        return str(stage["stage_id"]) if stage.get("stage_id") else None
    if provider == "pipedrive":
        payload = fetch({"path": f"/deals/{deal_id}", "params": {}}) or {}
        if payload.get("error_kind"):
            return None
        stage_id = (payload.get("data") or {}).get("stage_id")
        return str(stage_id) if stage_id not in (None, "") else None
    return None


def contact_inbound(connection: dict, contact_id: str) -> Optional[bool]:
    """Whether the CRM says the contact came in on its own. HubSpot only (original source);
    anything else, or an unset source, is unknown."""
    if str(connection.get("provider") or "") != "hubspot":
        return None
    payload = _fetch(connection)({
        "path": "/crm/v3/objects/contacts/batch/read",
        "json": {"properties": ["hs_analytics_source"], "inputs": [{"id": str(contact_id)}]},
    }) or {}
    if payload.get("error_kind"):
        return None
    for row in payload.get("results") or []:
        source = str((row.get("properties") or {}).get("hs_analytics_source") or "").strip().upper()
        if source:
            return source in _HUBSPOT_INBOUND_SOURCES
    return None


def build_context(
    supabase: Any,
    company_id: str,
    need: dict[str, bool],
    *,
    contact_id: Optional[str] = None,
    deal_id: Optional[str] = None,
    exclude_memo_id: Optional[str] = None,
) -> dict:
    """{contact, inbound, deal_stage}, each None when unknown or not needed."""
    context: dict = {"contact": None, "inbound": None, "deal_stage": None}
    if need["contact"]:
        context["contact"] = contact_status(
            supabase, company_id, contact_id=contact_id, deal_id=deal_id, exclude_memo_id=exclude_memo_id,
        )
    wants_stage = need["stage"] and deal_id
    wants_inbound = need["inbound"] and contact_id
    if wants_stage or wants_inbound:
        try:
            connection = crm_connection(supabase, company_id)
        except Exception:
            connection = None
        if connection:
            for name, wanted, read in (
                ("deal_stage", wants_stage, lambda: deal_stage_for(connection, str(deal_id))),
                ("inbound", wants_inbound, lambda: contact_inbound(connection, str(contact_id))),
            ):
                if not wanted:
                    continue
                try:
                    context[name] = read()
                except Exception:
                    logger.warning("playbook routing: CRM %s lookup failed", name, exc_info=True)
    return context


def resolve_motion(
    supabase: Any,
    company_id: str,
    *,
    sales_role: Optional[str],
    interaction_kind: str,
    contact_id: Optional[str] = None,
    deal_id: Optional[str] = None,
    exclude_memo_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], bool]:
    """(motion, "rule" | "role_default" | None, provisional) with the company's rules and
    what is known of the contact and deal. `provisional` = a signal some published rule for
    this role and channel depends on was unknown, so the answer may change once it is known.
    Raises on a broken rules read: the caller falls back to D5."""
    rules = load_rules(supabase, company_id)
    need = _needs(rules, sales_role, interaction_kind)
    context = build_context(
        supabase,
        company_id,
        need,
        contact_id=contact_id,
        deal_id=deal_id,
        exclude_memo_id=exclude_memo_id,
    )
    provisional = (
        (need["contact"] and context["contact"] is None)
        or (need["inbound"] and context["inbound"] is None)
        or (need["stage"] and context["deal_stage"] is None)
    )
    motion, why = route(sales_role, interaction_kind, context, rules)
    return motion, why, bool(provisional)


def merge_pin_meta(existing: Any, source: str, *, provisional: bool = False, **extra: Any) -> dict:
    """pipeline_meta with playbook_pin = {source, provisional?, ...}. Other keys are kept.
    source: "rule" | "role_default" | "manual". A "role_default" or provisional pin is one
    repin_before_c04 may still move; a manual one, or a rule match decided with everything
    it needed, never moves."""
    meta = dict(existing) if isinstance(existing, dict) else {}
    pin: dict = {"source": source}
    if provisional:
        pin["provisional"] = True
    meta[PIN_META_KEY] = {**pin, **extra}
    return meta


def is_repinnable(pipeline_meta: Any) -> bool:
    pin = pipeline_meta.get(PIN_META_KEY) if isinstance(pipeline_meta, dict) else None
    if not isinstance(pin, dict):
        return False
    return pin.get("source") == "role_default" or (pin.get("source") == "rule" and bool(pin.get("provisional")))


def repin_before_c04(supabase: Any, memo: dict) -> dict:
    """A memo pinned by the role default, or by a rule while the deal or contact was not
    known yet (Recall or desktop meetings), is routed again with what is known now, right
    before C04 reads its steps. Only a routing-flag pin marked "role_default" or provisional
    moves, and only to a published rule match: an explicit, manual or fully decided memo is
    left alone, and a second run finds the same answer, so it is a no-op. Never raises."""
    try:
        company_id = memo.get("company_id")
        memo_id = memo.get("id")
        if not company_id or not memo_id or not routing_enabled(supabase, company_id):
            return memo
        if not is_repinnable(memo.get("pipeline_meta")):
            return memo
        from app.services.captures import active_playbook_version, interaction_kind_of
        from app.services.company import sales_role_for_user
        from app.services.feature_flags import is_enabled

        if not is_enabled(supabase, company_id, SALES_ROLES_FLAG):
            return memo
        motion, why, provisional = resolve_motion(
            supabase,
            str(company_id),
            sales_role=sales_role_for_user(supabase, str(memo.get("user_id") or ""), company_id=str(company_id)),
            interaction_kind=interaction_kind_of(memo),
            contact_id=memo.get("hubspot_contact_id"),
            deal_id=memo.get("hubspot_deal_id") or memo.get("matched_deal_id"),
            exclude_memo_id=str(memo_id),
        )
        if why != "rule" or not motion or motion == memo.get("sales_motion_key"):
            return memo
        version = active_playbook_version(supabase, str(company_id), motion)
        if not version:
            return memo
        update = {
            "sales_motion_key": motion,
            "playbook_version_id": str(version),
            "pipeline_meta": merge_pin_meta(
                memo.get("pipeline_meta"), "rule", provisional=provisional, repinned_from=memo.get("sales_motion_key"),
            ),
        }
        supabase.table("memos").update(update).eq("id", str(memo_id)).execute()
        return {**memo, **update}
    except Exception:
        logger.warning("playbook re-pin failed", exc_info=True)
        return memo
