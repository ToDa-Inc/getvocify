"""The guided questions ("Lo que falta"): Vocify asks the Head of Sales what the playbook still lacks, one question at
a time, and each answer (typed, dictated, a PDF or an audio note) is applied to the draft.

An answer goes through the same "Dile a Vocify" path the editor uses (`fill_playbook`; `fill_company` for a figure two
documents disagree about), so it always saves, never rewrites what it was not about, and reaches the team only when
the draft is published. Every step is reversible: the content before an answer is kept in the session for `undo_gap`.

A session lives in `playbook_assistant_sessions` (kind `gaps`):
  state = {gaps: [Gap dict], answered: {key: {line, motion}}, skipped: [key], pending: {key: text},
           undo: {key: {...content before}}, motion_key, lang}
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.company import Membership
from app.services.playbooks.api_support import StructureRequest, company_context, product_context, read_source
from app.services.playbooks.assistant_store import AssistantStore
from app.services.playbooks.catalog import catalog_label
from app.services.playbooks.fill import FillError, fill_company, fill_playbook
from app.services.playbooks.gaps import MAX_GAPS, Gap, build_gaps, gap_from_dict, recent_suggest_events
from app.services.playbooks.repository import PlaybookRepository
from app.services.playbooks.structured import (
    PlaybookDraftError,
    editor_view,
    normalize_objections,
    normalize_qualification,
    normalize_steps,
)
from app.services.playbooks.versions import StaleDraftError

logger = logging.getLogger(__name__)

_LIVE_STATUSES = frozenset({"published", "paused", "draft"})


class AssistantError(Exception):
    """code: session_not_found | gap_not_found | nothing_to_undo"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# --- the session as the screen sees it ---------------------------------------------------------


def _remaining(state: dict) -> list[dict]:
    done = set(state.get("answered") or {}) | set(state.get("skipped") or [])
    return [g for g in state.get("gaps") or [] if g["key"] not in done]


def _public_gap(gap: dict) -> dict:
    return {key: gap.get(key) for key in ("key", "kind", "question", "seen", "example", "motion_key")}


def public_session(session: dict) -> dict:
    """{id, status, total, answered, skipped, current, pending_text}: what the screen needs and nothing of the
    model's instructions. `current` is the next question or None; `pending_text` is what the Head of Sales said for
    it if saving failed (so nothing they dictated is lost)."""
    state = session.get("state") or {}
    remaining = _remaining(state)
    current = remaining[0] if remaining else None
    return {
        "id": session["id"],
        "status": "open" if remaining else "done",
        "total": len(state.get("gaps") or []),
        "answered": len(state.get("answered") or {}),
        "skipped": len(state.get("skipped") or []),
        "current": _public_gap(current) if current else None,
        "pending_text": (state.get("pending") or {}).get(current["key"]) if current else None,
    }


def _load(store: AssistantStore, membership: Membership, session_id: str) -> dict:
    session = store.get_session(membership.company_id, session_id)
    if session is None or session.get("kind") != "gaps":
        raise AssistantError("session_not_found")
    return session


def _gap(state: dict, gap_key: str) -> dict:
    found = next((g for g in state.get("gaps") or [] if g["key"] == gap_key), None)
    if found is None:
        raise AssistantError("gap_not_found")
    return found


def _save(store: AssistantStore, membership: Membership, session: dict, state: dict) -> dict:
    status = "done" if not _remaining(state) else None
    return store.save_session(membership.company_id, session["id"], state=state, status=status)


# --- starting ----------------------------------------------------------------------------------


def _own_entries(repository: PlaybookRepository, company_id: str) -> list[dict]:
    entries: list[dict] = []
    for key, row in repository.list_types(company_id, include_draft=True).items():
        if row.get("status") in _LIVE_STATUSES:
            version = repository.editor_snapshot(company_id, key, include_draft=True).get("version")
            entries.extend(editor_view(version)["objections"])
    return entries


async def start_gaps_session(
    store: AssistantStore,
    repository: PlaybookRepository,
    supabase: Any,
    membership: Membership,
    *,
    motion_key: str,
    lang: str,
    events: Optional[list[dict]] = None,
    conflicts: Optional[list[Gap]] = None,
    limit: int = MAX_GAPS,
) -> dict:
    """The company's open session, or a new one with up to `limit` gaps. A session with nothing left to ask is
    created already done."""
    company_id = membership.company_id
    open_session = store.latest_open_session(company_id, "gaps")
    if open_session is not None:
        return open_session
    knowledge = (repository.get_knowledge(company_id) or {}).get("data") or {}
    gaps = build_gaps(
        entries=_own_entries(repository, company_id),
        knowledge=knowledge,
        events=events if events is not None else recent_suggest_events(supabase, company_id),
        lang=lang,
        limit=limit,
        conflicts=conflicts,
    )
    state = {
        "gaps": [g.as_dict() for g in gaps], "answered": {}, "skipped": [], "pending": {}, "undo": {},
        "motion_key": motion_key, "lang": lang,
    }
    session = store.create_session(company_id, membership.user_id, "gaps", state)
    return _save(store, membership, session, state) if not gaps else session


# --- answering ---------------------------------------------------------------------------------


def _motion_for(repository: PlaybookRepository, company_id: str, gap: Gap, state: dict) -> str:
    if gap.motion_key and (repository.list_types(company_id, include_draft=True).get(gap.motion_key) or {}).get("status") in _LIVE_STATUSES:
        return gap.motion_key
    return state["motion_key"]


def _content(repository: PlaybookRepository, company_id: str, key: str) -> tuple[dict, Optional[str]]:
    version = repository.editor_snapshot(company_id, key, include_draft=True).get("version")
    return editor_view(version), (version or {}).get("updated_at")


def _store_content(repository: PlaybookRepository, company_id: str, key: str, content: dict, base: Optional[str]) -> None:
    repository.save_draft(
        company_id,
        key,
        normalize_steps(content["steps"]) if content.get("steps") else [],
        normalize_objections(content.get("objections") or []),
        qualification=normalize_qualification(content.get("qualification") or []),
        base_updated_at=base,
    )


async def _apply_to_playbook(
    repository: PlaybookRepository, supabase: Any, company_id: str, motion: str, request: str, lang: str,
) -> tuple[dict, dict]:
    """The request applied to the draft of `motion` -> (the content before, the fill result). A draft that moved
    since it was read is read again once; a second conflict propagates."""
    row = repository.list_types(company_id, include_draft=True).get(motion) or {}
    if row.get("status") in (None, "missing"):
        repository.add_type(company_id, motion, catalog_label(motion, lang) or motion)
    for attempt in (0, 1):
        before, base = _content(repository, company_id, motion)
        result = await fill_playbook(motion, request, before, company_context(supabase, repository, company_id))
        if not result["changes"]:
            raise FillError("no_change")
        try:
            _store_content(repository, company_id, motion, result, base)
        except StaleDraftError:
            if attempt == 1:
                raise
            continue
        return before, result
    raise FillError("unreachable")  # pragma: no cover


async def _apply_to_company(repository: PlaybookRepository, supabase: Any, company_id: str, request: str) -> tuple[dict, dict]:
    row = repository.get_knowledge(company_id)
    before = (row or {}).get("data") or {}
    result = await fill_company(request, before, product_context(supabase, company_id))
    if not result["filled"]:
        raise FillError("no_change")
    repository.save_knowledge(company_id, result["knowledge"], base_updated_at=(row or {}).get("updated_at"))
    return before, result


async def answer_gap(
    store: AssistantStore,
    repository: PlaybookRepository,
    supabase: Any,
    membership: Membership,
    *,
    session_id: str,
    gap_key: str,
    source: StructureRequest,
) -> dict:
    """Applies the Head of Sales' answer to the draft (or to the company notes for a conflict) ->
    {saved_line, session, editor}. Reading the source can raise the same 422s as every upload (unreadable PDF, audio
    without speech): the session is then untouched. If saving fails after the text was read, the text stays in
    the session (`pending_text`) and the error propagates."""
    session = _load(store, membership, session_id)
    state = dict(session["state"])
    gap = gap_from_dict(_gap(state, gap_key))
    text = await read_source(source)
    company_id = membership.company_id
    request = f'{gap.request}\n\nManager says:\n"""\n{text}\n"""'
    try:
        if gap.kind == "conflict":
            before, result = await _apply_to_company(repository, supabase, company_id, request)
            motion, undo = None, {"kind": "knowledge", "data": before}
        else:
            motion = _motion_for(repository, company_id, gap, state)
            before, result = await _apply_to_playbook(repository, supabase, company_id, motion, request, state.get("lang") or "es")
            undo = {"kind": "playbook", "motion": motion, **{k: before.get(k) for k in ("steps", "objections", "qualification")}}
    except (StaleDraftError, FillError, PlaybookDraftError):
        state["pending"] = {**(state.get("pending") or {}), gap_key: text}
        store.save_session(company_id, session_id, state=state)
        raise
    line = str(result.get("summary") or "").strip() or "Guardado."
    state["answered"] = {**(state.get("answered") or {}), gap_key: {"line": line, "motion": motion}}
    state["undo"] = {**(state.get("undo") or {}), gap_key: undo}
    state["pending"] = {k: v for k, v in (state.get("pending") or {}).items() if k != gap_key}
    saved = _save(store, membership, session, state)
    editor = None
    if motion:
        content, _ = _content(repository, company_id, motion)
        editor = {"sales_motion_key": motion, **content}
    return {"saved_line": line, "session": public_session(saved), "editor": editor}


def skip_gap(store: AssistantStore, membership: Membership, *, session_id: str, gap_key: str) -> dict:
    """"Lo respondo luego": the question leaves this session and nothing changes."""
    session = _load(store, membership, session_id)
    state = dict(session["state"])
    _gap(state, gap_key)
    if gap_key not in (state.get("skipped") or []):
        state["skipped"] = [*(state.get("skipped") or []), gap_key]
    return public_session(_save(store, membership, session, state))


def undo_gap(store: AssistantStore, repository: PlaybookRepository, membership: Membership, *, session_id: str, gap_key: str) -> dict:
    """Puts back what an answer replaced and brings its question back."""
    session = _load(store, membership, session_id)
    state = dict(session["state"])
    _gap(state, gap_key)
    undo = (state.get("undo") or {}).get(gap_key)
    if not undo or gap_key not in (state.get("answered") or {}):
        raise AssistantError("nothing_to_undo")
    company_id = membership.company_id
    if undo["kind"] == "knowledge":
        repository.save_knowledge(company_id, undo["data"])
    else:
        _, base = _content(repository, company_id, undo["motion"])
        _store_content(repository, company_id, undo["motion"], undo, base)
    state["answered"] = {k: v for k, v in state["answered"].items() if k != gap_key}
    state["undo"] = {k: v for k, v in state["undo"].items() if k != gap_key}
    saved = store.save_session(company_id, session_id, state=state, status="open")
    return public_session(saved)
