"""Who to call, as data the Ask panel can act on. Built from the priority page, never from the model's text."""

from __future__ import annotations

from typing import Any, Optional

from app.services.crm_copilot.viewer import resolve_viewer
from app.services.feature_flags import is_enabled
from app.services.hubspot.account_info import build_contact_record_url
from app.services.pipedrive.record_urls import build_pipedrive_record_url, company_domain_from_api_domain

CALL_ACTIONS_FLAG = "ASK_CALL_ACTIONS_ENABLED"
MAX_CALL_TARGETS = 5
NOT_A_CALL_NOW = frozenset({"history_partial", "scheduled_no_early_call"})


def contact_url(connection: Optional[dict], connection_id: Any, contact_id: Any) -> Optional[str]:
    """Only the live connection's record. A row left over from another connection gets no link."""
    if not connection or not contact_id or str(connection.get("id") or "") != str(connection_id or ""):
        return None
    meta = connection.get("metadata") if isinstance(connection.get("metadata"), dict) else {}
    provider = str(connection.get("provider") or "").strip().lower()
    if provider == "hubspot":
        portal = meta.get("portal_id") or meta.get("hub_id")
        if not portal:
            return None
        return build_contact_record_url(
            str(portal), str(contact_id), ui_domain=meta.get("ui_domain"), region=meta.get("region") or "na1",
        )
    if provider == "pipedrive":
        domain = meta.get("company_domain") or company_domain_from_api_domain(meta.get("api_domain"))
        return build_pipedrive_record_url(domain, "person", str(contact_id)) if domain else None
    return None


def call_targets(page_items: list[dict], *, provider: Optional[str], connection: Optional[dict]) -> list[dict]:
    targets = []
    for row in page_items:
        if not row.get("contact_id") or row.get("reason") in NOT_A_CALL_NOW:
            continue
        targets.append({
            "contact_id": str(row["contact_id"]),
            "connection_id": row.get("connection_id"),
            "provider": provider,
            "contact_name": row.get("contact_name"),
            "reason": row.get("reason"),
            "next_action": row.get("next_action"),
            "crm_url": contact_url(connection, row.get("connection_id"), row["contact_id"]),
        })
        if len(targets) == MAX_CALL_TARGETS:
            break
    return targets


def record_call_targets(ctx: Any, targets: Optional[list[dict]]) -> None:
    """Turn-scoped: the last get_call_priorities of the turn wins."""
    try:
        ctx.call_targets = list(targets or [])
    except Exception:
        pass


def public_call_targets(ctx: Any, *, kind: str) -> Optional[list[dict]]:
    if kind != "text":
        return None
    targets = getattr(ctx, "call_targets", None)
    if not targets:
        return None
    viewer = resolve_viewer(ctx)
    if viewer is None or not is_enabled(getattr(ctx, "supabase", None), viewer.company_id, CALL_ACTIONS_FLAG):
        return None
    return list(targets)
