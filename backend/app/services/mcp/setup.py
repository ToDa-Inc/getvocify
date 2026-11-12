"""The company's setup over MCP: read it, and edit playbooks, «Cómo trabajamos», Vuestra empresa, the offer and settings.

Every operation calls the dashboard's own route handler (app.api.playbooks, playbook_company, playbook_rules, company,
auth) with the caller's membership, so validation, normalization (normalize_steps, normalize_objections,
normalize_qualification, normalize_knowledge, conduct.normalize), permissions (owner/admin) and cache invalidation are
the ones the dashboard runs, not a second copy. What this module adds is only what an agent needs around them:
a list left out keeps what is stored, the answer says what changed, and an HTTPException becomes a SetupError
carrying the API's own code.

The handlers are async but read the database synchronously, so the server runs each operation on a worker thread
with its own loop (server._run_async_in_thread).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import HTTPException
from pydantic import ValidationError

LIFECYCLE = ("discard_draft", "pause", "resume", "delete", "restore")

_HINTS = {
    "forbidden": "Only owners and admins of this Vocify workspace can change its setup.",
    "not_found": "No such call type in this workspace. Call get_setup to see the sales_motion_key of each one.",
    "stale_draft": "The draft changed since you read it (someone edited it in Vocify). Call get_setup with this "
    "sales_motion_key again and make your change on top of what it returns.",
    "stale_knowledge": "Vuestra empresa was saved by someone else since you read it. Call get_setup again and make "
    "your change on top of what it returns.",
    "no_draft": "There is no draft to publish. Save one with save_playbook_draft first.",
    "contradiction": "The draft has contradicting steps. Fix them with save_playbook_draft before publishing.",
    "not_published": "That only applies to a published playbook.",
    "not_paused": "That playbook is not paused.",
    "not_archived": "That playbook is not deleted, so there is nothing to restore.",
    "not_activated": "«Cómo trabajamos» is not available on this workspace yet.",
    "bad_rule": "applies_to does not fit the rule schema: {role: sdr|ae|any, channels: [call|meeting|visit], contact: "
    "new|contacted|inbound|any, deal_stages: [stage ids]}.",
    "rule_required": "A call type outside Vocify's catalog needs applies_to (when it applies).",
    "channel_required": "A call type needs at least one channel: call or meeting.",
    "type_edit_unavailable": "This workspace does not use types by channel, so only applies_to can change on an "
    "existing type.",
    "invalid": "The request does not fit the expected shape.",
}


class SetupError(Exception):
    """An expected refusal. `code` is the API's own error code; the message is for the agent to act on."""

    def __init__(self, code: str, message: str = "", *, status: int = 422):
        self.code = code
        self.status = status
        super().__init__(f"{code}: {message or _HINTS.get(code) or code}")


def _from_http(exc: HTTPException, *, conflict_code: Optional[Callable[[str], str]] = None) -> SetupError:
    detail = exc.detail
    if isinstance(detail, dict) and detail.get("code"):
        code = str(detail["code"])
        where = [f"{name} {detail[name]}" for name in ("index", "field") if detail.get(name) is not None]
        hint = _HINTS.get(code, "")
        if where:
            hint = f"{hint} (at {', '.join(where)})".strip()
        return SetupError(code, hint, status=exc.status_code)
    text = str(detail or "")
    if exc.status_code == 403:
        return SetupError("forbidden", status=403)
    if exc.status_code == 404:
        return SetupError("not_found", status=404)
    if exc.status_code == 409 and conflict_code:
        return SetupError(conflict_code(text), status=409)
    return SetupError("invalid" if exc.status_code == 422 else "conflict", text, status=exc.status_code)


async def _run(make: Callable[[], Any], **kwargs: Any) -> Any:
    try:
        return await make()
    except HTTPException as exc:
        raise _from_http(exc, **kwargs) from exc


def _model(cls: type, **values: Any) -> Any:
    """A request model of the API, built from what the agent sent: its validation is the API's."""
    try:
        return cls(**values)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5])
        raise SetupError("invalid", problems) from exc


# ----- what changed ---------------------------------------------------------------------------------------


def _keyed(items: Any, key: Callable[[dict], str]) -> dict[str, dict]:
    return {key(item): item for item in items or [] if isinstance(item, dict)}


def _list_changes(before: Any, after: Any, key: Callable[[dict], str]) -> Optional[dict]:
    old, new = _keyed(before, key), _keyed(after, key)
    out = {
        "added": [k for k in new if k not in old],
        "removed": [k for k in old if k not in new],
        "changed": [k for k in new if k in old and new[k] != old[k]],
    }
    if not any(out.values()) and list(old) != list(new):
        out["reordered"] = True
    out = {name: value for name, value in out.items() if value}
    return out or None


def _objection_key(item: dict) -> str:
    return f"custom:{item.get('id')}" if item.get("category") == "custom" else str(item.get("category"))


_LISTS: dict[str, Callable[[dict], str]] = {
    "steps": lambda item: str(item.get("step_id")),
    "objections": _objection_key,
    "qualification": lambda item: str(item.get("criterion_id")),
}


def changes(before: Optional[dict], after: Optional[dict], fields: tuple[str, ...]) -> dict:
    """{field: what changed} for the fields that differ. A list of steps, objections or criteria says which ids were
    added, removed or changed; any other field just reports that it changed (its new value is in the answer)."""
    before, after = before or {}, after or {}
    out: dict = {}
    for field in fields:
        old, new = before.get(field), after.get(field)
        if old == new:
            continue
        out[field] = _list_changes(old, new, _LISTS[field]) if field in _LISTS else "changed"
        if out[field] is None:
            out.pop(field)
    return out


_EDITOR_FIELDS = ("steps", "objections", "qualification")
_CONDUCT_FIELDS = ("goal", "also_good", "stop_when", "criteria", "core", "situations")
_SETTINGS_FIELDS = ("name", "sales_strategy", "callback_after_days", "followup_cadence", "auto_create_contact_company")


# ----- reading ------------------------------------------------------------------------------------------------


async def _overview(supabase: Any, membership: Any) -> dict:
    from app.api.playbooks import list_playbooks

    return await _run(lambda: list_playbooks(supabase=supabase, membership=membership))


async def _editor(supabase: Any, membership: Any, key: str) -> dict:
    from app.api.playbooks import get_playbook_editor

    return await _run(lambda: get_playbook_editor(key, live=False, supabase=supabase, membership=membership))


async def _conduct(supabase: Any, membership: Any, key: str) -> Optional[dict]:
    """«Cómo trabajamos» for a manager; None for anyone else or before it exists on the workspace."""
    from app.api.playbooks import get_playbook_conduct
    from app.services.playbooks.versions import can_publish

    if not can_publish(membership.role):
        return None
    try:
        return (await _run(lambda: get_playbook_conduct(key, supabase=supabase, membership=membership)))["conduct"]
    except SetupError as exc:
        if exc.code == "not_activated":
            return None
        raise


async def _knowledge(membership: Any) -> dict:
    from app.api.playbook_company import get_company_knowledge

    return await _run(lambda: get_company_knowledge(membership=membership))


async def _company_settings(supabase: Any, membership: Any) -> dict:
    from app.api.company import get_company
    from app.services.company import CompanyService

    shown = await _run(lambda: get_company(user_id=membership.user_id, supabase=supabase))
    row = CompanyService(supabase).get_company(membership.company_id)
    return {
        "name": shown.name,
        "sales_strategy": shown.sales_strategy,
        "callback_after_days": shown.callback_after_days,
        "followup_cadence": getattr(shown, "followup_cadence", None),
        "auto_create_contact_company": bool(row.get("auto_create_contact_company", False)),
    }


def _offer(supabase: Any, company_id: str) -> str:
    from app.services.playbooks.api_support import product_context

    return product_context(supabase, company_id)


async def get_setup(supabase: Any, membership: Any, key: Optional[str], *, can_write: bool) -> dict:
    from app.services.playbooks.versions import can_publish

    edit = {"can_edit": can_publish(membership.role), "connection_can_edit": can_write}
    if key:
        overview = await _overview(supabase, membership)
        return {
            "sales_motion_key": key,
            "type": {"state": overview["motions"].get(key), **(overview["details"].get(key) or {})},
            "playbook": await _editor(supabase, membership, key),
            "conduct": await _conduct(supabase, membership, key),
            **edit,
        }
    knowledge = await _knowledge(membership)
    return {
        "playbooks": await _overview(supabase, membership),
        "company_knowledge": knowledge,
        "offer": _offer(supabase, membership.company_id),
        "settings": await _company_settings(supabase, membership),
        **edit,
    }


# ----- playbooks ------------------------------------------------------------------------------------------


def _dump(items: Optional[list]) -> Optional[list[dict]]:
    return None if items is None else [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in items]


async def save_playbook_draft(
    supabase: Any,
    membership: Any,
    key: str,
    *,
    steps: Optional[list] = None,
    objections: Optional[list] = None,
    qualification: Optional[list] = None,
    base_updated_at: Optional[str] = None,
) -> dict:
    """PUT /playbooks/{key}/draft. A list left out keeps what the draft (else the live version) has; one sent replaces
    that list. Without base_updated_at, the version read here is the base, so an edit made meanwhile is a stale_draft."""
    from app.api.playbooks import StructuredDraftRequest, save_structured_playbook_draft

    if steps is None and objections is None and qualification is None:
        raise SetupError("invalid", "Send at least one of steps, objections or qualification.")
    before = await _editor(supabase, membership, key)
    body = _model(
        StructuredDraftRequest,
        steps=_dump(steps) if steps is not None else before["steps"],
        objections=_dump(objections) if objections is not None else before["objections"],
        qualification=_dump(qualification),
        base_updated_at=base_updated_at or before.get("updated_at"),
    )
    after = await _run(lambda: save_structured_playbook_draft(key, body, membership=membership))
    return {"changed": changes(before, after, _EDITOR_FIELDS), "playbook": after}


def _publish_conflict(detail: str) -> str:
    # publish answers 409 with a sentence for the dashboard: contradicting steps, or no draft.
    return "contradiction" if "contradict" in detail.lower() else "no_draft"


async def publish_playbook(supabase: Any, membership: Any, key: str) -> dict:
    """POST /playbooks/{key}/publish: the draft becomes the version every new call is coached and scored with."""
    from app.api.playbooks import publish_motion

    result = await _run(lambda: publish_motion(key, membership=membership), conflict_code=_publish_conflict)
    return {
        "published": key,
        "version_id": (result.get("activated") or {}).get(key),
        "state": (result.get("motions") or {}).get(key),
        "playbook": await _editor(supabase, membership, key),
    }


async def set_playbook_state(supabase: Any, membership: Any, key: str, action: str) -> dict:
    from app.api import playbooks

    if action not in LIFECYCLE:
        raise SetupError("invalid", f"action must be one of {', '.join(LIFECYCLE)}.")
    before = await _overview(supabase, membership)
    if action == "discard_draft":
        editor = await _run(lambda: playbooks.discard_structured_playbook_draft(key, membership=membership))
        return {"action": action, "sales_motion_key": key, "playbook": editor}
    handler = {
        "pause": playbooks.pause_playbook,
        "resume": playbooks.resume_playbook,
        "delete": playbooks.delete_playbook,
        "restore": playbooks.restore_playbook,
    }[action]
    after = await _run(lambda: handler(key, supabase=supabase, membership=membership))
    return {
        "action": action,
        "sales_motion_key": key,
        "state": {"before": before["motions"].get(key), "after": after["motions"].get(key)},
    }


async def save_call_type(
    supabase: Any,
    membership: Any,
    key: str,
    *,
    name: Optional[str] = None,
    channels: Optional[list[str]] = None,
    recognize: Optional[str] = None,
    applies_to: Optional[dict] = None,
) -> dict:
    """Creates the call type when the workspace does not have it (POST /playbooks/types), else edits it: its name,
    channels and recognition sentence (PATCH /{key}/type, types by channel) and its rule (PUT /{key}/rule)."""
    from app.api import playbook_rules, playbooks
    from app.services.feature_flags import is_enabled
    from app.services.playbooks import channel_types

    key = (key or "").strip()
    if not key:
        raise SetupError("invalid", "sales_motion_key is required.")
    before = await _overview(supabase, membership)
    if key not in before["motions"]:
        body = _model(
            playbooks.TypeRequest, type_key=key, name=name or "", applies_to=applies_to, channels=channels, recognize=recognize,
        )
        await _run(lambda: playbooks.create_type(body, supabase=supabase, membership=membership))
        created = True
    else:
        created = False
        by_channel = is_enabled(supabase, membership.company_id, channel_types.FLAG)
        if name is not None or channels is not None or recognize is not None:
            if not by_channel:
                raise SetupError("type_edit_unavailable")
            edit = _model(playbooks.TypeEdit, label=name, channels=channels, recognize=recognize)
            await _run(lambda: playbooks.edit_type(key, edit, supabase=supabase, membership=membership))
        if applies_to is not None:
            rule = _model(playbook_rules.RuleRequest, applies_to=applies_to)
            await _run(lambda: playbook_rules.put_rule(key, rule, membership=membership))
    after = await _overview(supabase, membership)
    old, new = before["details"].get(key) or {}, after["details"].get(key) or {}
    return {
        "sales_motion_key": key,
        "created": created,
        "changed": sorted(name for name in set(old) | set(new) if old.get(name) != new.get(name)),
        "type": {"state": after["motions"].get(key), **new},
    }


async def save_conduct(supabase: Any, membership: Any, key: str, sent: dict) -> dict:
    """PUT /playbooks/{key}/conduct. The handler keeps the stored core and situations when they are not sent; for an
    agent every part left out keeps what is stored, so the other parts are filled from the current value."""
    from app.api.playbooks import save_playbook_conduct
    from app.services.playbooks.conduct import Conduct

    if not sent:
        raise SetupError("invalid", "Send at least one part of «Cómo trabajamos».")
    before = await _conduct(supabase, membership, key)
    current = before or {}
    body = _model(Conduct, **{**{name: current[name] for name in _CONDUCT_FIELDS if name in current}, **sent})
    after = (await _run(lambda: save_playbook_conduct(key, body, supabase=supabase, membership=membership)))["conduct"]
    return {"changed": changes(before, after, _CONDUCT_FIELDS), "conduct": after}


# ----- the company -------------------------------------------------------------------------------------------


async def update_company(
    supabase: Any,
    membership: Any,
    *,
    knowledge: Optional[dict] = None,
    base_updated_at: Optional[str] = None,
    offer: Optional[str] = None,
    settings: Optional[dict] = None,
) -> dict:
    """Vuestra empresa (PUT /playbooks/company: the sections sent replace those sections, the others stay), the offer
    and the CRM option (PATCH /auth/me's company fields), and the company settings (PATCH /company)."""
    from app.api import auth, company, playbook_company
    from app.services.playbooks.versions import can_publish

    settings = dict(settings or {})
    if knowledge is None and offer is None and not settings:
        raise SetupError("invalid", "Send knowledge, offer or settings.")
    if not can_publish(membership.role):
        raise SetupError("forbidden", status=403)  # before any part is written, so nothing is half saved
    unknown = set(settings) - set(_SETTINGS_FIELDS)
    if unknown:
        raise SetupError("invalid", f"Unknown settings: {', '.join(sorted(unknown))}. Known: {', '.join(_SETTINGS_FIELDS)}.")
    shared = {name: value for name, value in (("product_context", offer), ("auto_create_contact_company", settings.pop("auto_create_contact_company", None))) if value is not None}
    shared_body = _model(auth.UpdateProfileRequest, **shared) if shared else None
    company_body = _model(company.UpdateCompanyRequest, **settings) if settings else None
    out: dict = {"changed": {}}

    if knowledge is not None:
        from app.services.playbooks.knowledge import SECTION_ORDER

        if not isinstance(knowledge, dict) or not knowledge:
            raise SetupError("invalid", "knowledge is an object of sections, e.g. {\"icp\": \"...\"}.")
        unknown = set(knowledge) - set(SECTION_ORDER)
        if unknown:
            raise SetupError("invalid", f"Unknown sections: {', '.join(sorted(unknown))}. Known: {', '.join(SECTION_ORDER)}.")
        before = await _knowledge(membership)
        body = _model(
            playbook_company.CompanyKnowledgeRequest,
            knowledge={**before["knowledge"], **knowledge},
            base_updated_at=base_updated_at or before.get("updated_at"),
        )
        after = await _run(lambda: playbook_company.put_company_knowledge(body, membership=membership))
        out["changed"]["knowledge"] = [key for key in SECTION_ORDER if before["knowledge"].get(key) != after["knowledge"].get(key)]
        out["company_knowledge"] = after
        if after.get("trimmed"):
            out["trimmed"] = after["trimmed"]  # what was cut for size: tell the caller, never save less in silence

    if shared_body is not None or company_body is not None:
        before_settings = await _company_settings(supabase, membership)
        before_offer = _offer(supabase, membership.company_id)
        if shared_body is not None:
            updates = shared_body.model_dump(exclude_none=True)
            try:
                auth.save_shared_company_settings(supabase, membership, updates)
            except HTTPException as exc:
                raise _from_http(exc) from exc
        if company_body is not None:
            await _run(lambda: company.update_company(company_body, user_id=membership.user_id, supabase=supabase))
        after_settings = await _company_settings(supabase, membership)
        after_offer = _offer(supabase, membership.company_id)
        if offer is not None:
            out["changed"]["offer"] = before_offer != after_offer
            out["offer"] = after_offer
        moved = [name for name in _SETTINGS_FIELDS if before_settings.get(name) != after_settings.get(name)]
        if moved:
            out["changed"]["settings"] = moved
        out["settings"] = after_settings
        ignored = [name for name in settings if before_settings.get(name) is None and after_settings.get(name) is None]
        if ignored:
            out["not_available"] = ignored  # the feature behind these settings is off for this workspace
    return out
