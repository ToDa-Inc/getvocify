"""Which interaction types each member runs, and the role the rest of the product reads that follows from them."""

from __future__ import annotations

from typing import Any, Optional

from app.services.playbooks.repository import PlaybookRepository
from app.services.sales_process.logic import assigned_types, role_from_types
from app.services.sales_process.process import process_view
from app.services.sales_process.store import SalesProcessStore


def derive_for_invite(store: SalesProcessStore, repository: PlaybookRepository, company_id: str, types: Optional[list[str]]) -> tuple[Optional[list[str]], str]:
    """(the types that exist among `types`, the role they imply). Nothing chosen, or nothing that exists, is every type."""
    view = process_view(repository, store, company_id)
    stages = {item["key"]: item["stage"] for item in view}
    cleaned = assigned_types(types, stages)
    return cleaned, role_from_types(cleaned, lambda key: stages.get(key, "first_contact"))


def carry_invite_types(store: SalesProcessStore, company_id: str, invitation_id: str, user_id: str) -> None:
    """The invited person accepted: what they were invited to run becomes theirs, and the invitation keeps nothing."""
    types = store.get_member_types(company_id, invitation_id=invitation_id)
    if types:
        store.set_member_types(company_id, types, user_id=user_id)
        store.set_member_types(company_id, None, invitation_id=invitation_id)


def set_member_types(
    store: SalesProcessStore, repository: PlaybookRepository, company_service: Any, actor: Any, company_id: str, member_id: str, types: Optional[list[str]],
) -> dict:
    """Saves what a member runs and writes the role that follows (when the company uses sales roles) through the same path as
    editing a profile, so a SDR turned AE releases what a SDR held. -> {types, sales_role}."""
    row = company_service._get_member_row(company_id, member_id)
    cleaned, role = derive_for_invite(store, repository, company_id, types)
    store.set_member_types(company_id, cleaned, user_id=str(row["user_id"]))
    if company_service.sales_roles_enabled(company_id):
        company_service.update_member_profile(company_id=company_id, actor=actor, member_id=member_id, sales_role=role)
    return {"types": cleaned, "sales_role": role}


def before_invite(supabase: Any, company_id: str, types: Optional[list[str]]) -> tuple[Optional[list[str]], Optional[str]]:
    """For the invitation form: the types to keep and the role to store on the invitation, or (None, None) when the company
    does not use the editable process or its tables are not there yet (the invitation then goes as it always did)."""
    from app.services.feature_flags import is_enabled
    from app.services.playbooks.repository import get_playbook_repository
    from app.services.sales_process.store import SalesProcessUnavailable, get_sales_process_store

    if types is None or not is_enabled(supabase, company_id, "SALES_PROCESS_ENABLED"):
        return None, None
    try:
        return derive_for_invite(get_sales_process_store(supabase), get_playbook_repository(), company_id, types)
    except SalesProcessUnavailable:
        return None, None


def keep_invite_types(supabase: Any, company_id: str, invitation_id: str, types: Optional[list[str]]) -> None:
    from app.services.sales_process.store import SalesProcessUnavailable, get_sales_process_store

    if types:
        try:
            get_sales_process_store(supabase).set_member_types(company_id, types, invitation_id=invitation_id)
        except SalesProcessUnavailable:
            pass


def hand_over_invite_types(supabase: Any, company_id: str, invitation_id: str, user_id: str) -> None:
    """After an invitation is accepted. Never fails the acceptance: the person is in, their types are a convenience."""
    import logging

    from app.services.sales_process.store import get_sales_process_store

    try:
        carry_invite_types(get_sales_process_store(supabase), company_id, invitation_id, user_id)
    except Exception as exc:
        logging.getLogger(__name__).warning("invite types not handed over: %s", type(exc).__name__)


def assigned_for(supabase: Any, company_id: str, user_id: Optional[str]) -> Optional[list[str]]:
    """The types a person runs, or None (= all): no person, the editable process off, nothing assigned or tables not there.
    Never raises: a failed read is "all", the way everything worked before."""
    if not user_id:
        return None
    try:
        from app.services.feature_flags import is_enabled
        from app.services.sales_process.store import get_sales_process_store

        if not is_enabled(supabase, company_id, "SALES_PROCESS_ENABLED"):
            return None
        return get_sales_process_store(supabase).get_member_types(company_id, user_id=str(user_id))
    except Exception:
        return None
