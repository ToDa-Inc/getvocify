"""The playbooks repository: one interface, two implementations, one contract suite.

`PlaybookRepository` is what the API needs from storage, nothing more. `SqlPlaybookRepository` is what runs in
production: every operation is ONE call to a SQL function of migration 066_playbooks_v2 (a transaction each; the
conflict checks live inside the write), so there is no multi-step write in Python. `InMemoryPlaybookRepository` is a
TEST FAKE with the same semantics, for the API tests; tests/playbooks/test_repository_contract.py runs the same
scenarios against both (the SQL one against a real PostgreSQL), so they cannot diverge.

What decides whether a playbook applies to a call is not here: see services/playbooks/live.py.

Errors, whichever implementation: StaleDraftError, StaleKnowledgeError, LifecycleError (not_published, not_paused,
not_archived, not_found), PublishError (contradiction, not_a_draft, empty_type) and PlaybookRepositoryError (anything
else the storage refuses, e.g. a malformed item of an intake).
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol, runtime_checkable

from app.services.playbooks.knowledge import StaleKnowledgeError, normalize_knowledge
from app.services.playbooks.structured import editor_view, render_text
from app.services.playbooks.versions import (
    LifecycleError,
    PublishError,
    StaleDraftError,
    parse_ts,
    same_instant,
)

logger = logging.getLogger(__name__)

SOURCE_PREFIX = "source:"
UNSET: Any = object()
"""Marks "not given" for label / applies_to (None is a value: it clears the field)."""

LIFECYCLE_ACTIONS = ("pause", "resume", "archive", "restore")
_LIFECYCLE_CODES = frozenset({"not_published", "not_paused", "not_archived", "not_found"})
_PUBLISH_CODES = frozenset({"contradiction", "not_a_draft", "empty_type"})
_REPOSITORY_CODES = frozenset({"invalid_type_item", "invalid_action"})


class PlaybookRepositoryError(Exception):
    """The storage refused the operation for a reason that is not one of the business outcomes above."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def summarize(version: Optional[dict], *, has_draft: bool, paused: bool) -> dict:
    """What the list shows of a type: how many steps, objection answers and qualification criteria the version the
    editor opens has (counted the way the editor shows them), whether a pending draft exists and whether the type
    is paused."""
    view = editor_view(version)
    return {
        "step_count": len(view["steps"]),
        "answer_count": len(view["objections"]),
        "criteria_count": len(view["qualification"]),
        "has_draft": has_draft,
        "paused": paused,
    }


def _type_row(entry: dict) -> dict:
    return {
        "status": entry["status"],
        "label": entry.get("label") or None,
        "applies_to": entry.get("applies_to"),
        **summarize(entry.get("version"), has_draft=bool(entry.get("has_draft")), paused=bool(entry.get("paused"))),
    }


def _version_view(row: Optional[dict]) -> Optional[dict]:
    """A stored version as every caller reads it: {id, status, steps, entries, qualification, created_at, updated_at}."""
    if not row:
        return None
    return {
        "id": str(row["id"]),
        "status": row.get("status"),
        "steps": list(row.get("steps") or []),
        "entries": list(row.get("entries") or []),
        "qualification": list(row.get("qualification") or []),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _knowledge_view(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return None
    return {
        "data": normalize_knowledge(row.get("data")),
        "source_id": row.get("source_id"),
        "updated_at": row.get("updated_at"),
    }


def _base_iso(base_updated_at: Optional[str]) -> Optional[str]:
    """The caller's base as an ISO instant, None when not given. A base that cannot be read can only be stale."""
    if not base_updated_at:
        return None
    parsed = parse_ts(base_updated_at)
    if parsed is None:
        raise StaleDraftError()
    return parsed.isoformat()


def _intake_text(item: dict) -> str:
    if not isinstance(item.get("steps"), list) or not isinstance(item.get("entries"), list):
        return ""  # malformed: the storage refuses the item (invalid_type_item), not the renderer
    return render_text(item["steps"], item["entries"], item.get("qualification") or [])


@runtime_checkable
class PlaybookRepository(Protocol):
    """Everything the playbooks API reads and writes. Company-scoped: every method takes the company id.

    Shapes (plain dicts):
      type row        {status, label, applies_to, step_count, answer_count, criteria_count, has_draft, paused}
                      status: published | paused | draft | missing
      version         {id, status, steps, entries, qualification, created_at, updated_at}
      editor snapshot {state: draft|published|empty, version|None, has_live, source: {id, kind, name}|None, paused}
      knowledge       {data, source_id, updated_at}
    """

    # -- the list and the editor ----------------------------------------------------------------

    def list_types(self, company_id: str, *, include_draft: bool = True) -> dict[str, dict]:
        """key -> type row for every type of the company that is not deleted. With include_draft (managers) the
        counts and has_draft describe the pending draft when there is one; without it (a rep) only the version that
        is published (also when paused) and has_draft is always False."""

    def editor_snapshot(self, company_id: str, key: str, *, include_draft: bool) -> dict: ...

    # -- drafts and publishing --------------------------------------------------------------------

    def save_draft(
        self,
        company_id: str,
        key: str,
        steps: list,
        entries: list,
        *,
        qualification: Optional[list] = None,
        source_id: Optional[str] = None,
        base_updated_at: Optional[str] = None,
    ) -> dict:
        """Saves the editor's draft and returns the version row. A pending draft is updated in place; else a new
        one is created. A deleted type comes back empty and switched on. `qualification` None keeps the draft's
        criteria (a new draft starts from the published version's). StaleDraftError when `base_updated_at` is not
        the updated_at of the draft (or, for a first save over a published version, of that version)."""

    def discard_draft(self, company_id: str, key: str) -> bool:
        """Deletes the pending draft (never a published version). True when something was deleted."""

    def publish(self, company_id: str, key: str) -> str:
        """Publishes the pending draft; the type is on afterwards. Returns the version id. PublishError
        `not_a_draft` (nothing pending, deleted or unknown type) or `contradiction`."""

    def set_state(self, company_id: str, key: str, action: str) -> None:
        """pause | resume | archive | restore (see the migration). LifecycleError with the codes not_published,
        not_paused, not_found, not_archived."""

    # -- types, names and rules -------------------------------------------------------------------

    def add_type(self, company_id: str, key: str, name: str, *, label: Any = UNSET, applies_to: Any = UNSET) -> None:
        """Adds a type (or brings a deleted one back, empty), with its name and rule in the same step when given.
        PublishError `empty_type` for an empty key."""

    def set_meta(self, company_id: str, key: str, *, label: Any = UNSET, applies_to: Any = UNSET) -> None:
        """The type's name and/or routing rule. Creates the type when it has no row yet."""

    # -- the material a playbook was structured from ---------------------------------------------

    def save_source(self, company_id: str, key: Optional[str], kind: str, name: Optional[str], text: str) -> dict:
        """Keeps the original document. Creates no version. `key` None = a document for the whole company."""

    def get_source(self, company_id: str, source_id: Optional[str]) -> Optional[dict]: ...

    def get_import(self, company_id: str, import_id: str) -> Optional[dict]: ...

    def save_import(self, company_id: str, record: dict, key: Optional[str]) -> None:
        """The legacy text import: a draft made of the whole document, for `key`. Idempotent per import id."""

    # -- what Vocify knows about the company -------------------------------------------------------

    def get_knowledge(self, company_id: str) -> Optional[dict]: ...

    def save_knowledge(self, company_id: str, data: dict, *, base_updated_at: Optional[str] = None) -> dict:
        """Replaces the company's knowledge (normalized here). StaleKnowledgeError when `base_updated_at` is not the
        saved row's updated_at (a base with no row is stale too)."""

    # -- one input for the whole company ---------------------------------------------------------

    def save_intake(
        self, company_id: str, types: list[dict], knowledge: Optional[dict], source_id: Optional[str],
    ) -> dict:
        """Saves every detected type's draft and the (already merged) company knowledge in ONE transaction: if any
        item fails nothing is saved. `types`: [{key, steps, entries, qualification (None = keep), ensure: {name,
        label?, applies_to?} | None}]; `ensure` creates the type first when the company does not have it. Returns
        {types: [{sales_motion_key, version_id}], knowledge: knowledge | None}. PlaybookRepositoryError for a
        malformed item."""


# ─── SQL ──────────────────────────────────────────────────────────────────────────────────────


def _error_code(exc: Exception) -> Optional[str]:
    """The RAISE EXCEPTION text of a failed rpc (postgrest's APIError.message), None for any other failure."""
    message = getattr(exc, "message", None)
    if not message and exc.args and isinstance(exc.args[0], dict):
        message = exc.args[0].get("message")
    return str(message).strip() if message else None


def _translate(exc: Exception) -> Exception:
    code = _error_code(exc)
    if code == "stale_draft":
        return StaleDraftError()
    if code == "stale_knowledge":
        return StaleKnowledgeError()
    if code in _LIFECYCLE_CODES:
        return LifecycleError(code)
    if code in _PUBLISH_CODES:
        return PublishError(code)
    if code in _REPOSITORY_CODES:
        return PlaybookRepositoryError(code)
    return exc


class SqlPlaybookRepository:
    """Production: thin calls to the SQL functions of migration 066_playbooks_v2 through Supabase's `rpc`."""

    def __init__(self, supabase):
        self.supabase = supabase

    def _rpc(self, name: str, params: dict) -> Any:
        try:
            result = self.supabase.rpc(name, params).execute()
        except Exception as exc:
            translated = _translate(exc)
            if translated is exc:
                raise
            raise translated from exc
        return getattr(result, "data", None)

    # -- the list and the editor

    def list_types(self, company_id: str, *, include_draft: bool = True) -> dict[str, dict]:
        entries = self._rpc("playbook_overview", {"p_company": company_id, "p_include_draft": include_draft}) or []
        return {entry["key"]: _type_row(entry) for entry in entries}

    def editor_snapshot(self, company_id: str, key: str, *, include_draft: bool) -> dict:
        data = self._rpc(
            "playbook_editor", {"p_company": company_id, "p_motion": key, "p_include_draft": include_draft},
        ) or {}
        return {
            "state": data.get("state") or "empty",
            "version": _version_view(data.get("version")),
            "has_live": bool(data.get("has_live")),
            "source": data.get("source"),
            "paused": bool(data.get("paused")),
        }

    # -- drafts and publishing

    def save_draft(
        self, company_id, key, steps, entries, *, qualification=None, source_id=None, base_updated_at=None,
    ) -> dict:
        row = self._rpc(
            "playbook_save_draft",
            {
                "p_company": company_id,
                "p_motion": key,
                "p_steps": steps,
                "p_entries": entries,
                "p_qualification": qualification,
                "p_source_id": source_id,
                "p_base_updated_at": _base_iso(base_updated_at),
                "p_text": render_text(steps, entries, qualification or []),
            },
        )
        return _version_view(row)  # type: ignore[return-value]

    def discard_draft(self, company_id: str, key: str) -> bool:
        return bool(self._rpc("playbook_discard_draft", {"p_company": company_id, "p_motion": key}))

    def publish(self, company_id: str, key: str) -> str:
        outcome = self._rpc("publish_playbook_motion", {"p_company": company_id, "p_motion": key})
        if isinstance(outcome, list):
            outcome = outcome[0] if outcome else None
        if not (isinstance(outcome, str) and outcome.startswith("published:")):
            raise PublishError("not_a_draft")
        return outcome.split(":", 1)[1]

    def set_state(self, company_id: str, key: str, action: str) -> None:
        self._rpc("playbook_set_state", {"p_company": company_id, "p_motion": key, "p_action": action})

    # -- types, names and rules

    @staticmethod
    def _meta(label: Any, applies_to: Any) -> Optional[dict]:
        meta: dict = {}
        if label is not UNSET:
            meta["label"] = label
        if applies_to is not UNSET:
            meta["applies_to"] = applies_to
        return meta or None

    def add_type(self, company_id, key, name, *, label=UNSET, applies_to=UNSET) -> None:
        self._rpc(
            "playbook_add_type",
            {"p_company": company_id, "p_key": key, "p_name": name, "p_meta": self._meta(label, applies_to)},
        )

    def set_meta(self, company_id, key, *, label=UNSET, applies_to=UNSET) -> None:
        meta = self._meta(label, applies_to)
        if meta:
            self._rpc("playbook_set_meta", {"p_company": company_id, "p_motion": key, "p_meta": meta})

    # -- sources and imports

    def save_source(self, company_id, key, kind, name, text) -> dict:
        return self._rpc(
            "playbook_source_save",
            {"p_company": company_id, "p_motion": key, "p_kind": kind, "p_name": name or "", "p_text": text},
        )

    def get_source(self, company_id, source_id) -> Optional[dict]:
        if not source_id or not str(source_id).startswith(SOURCE_PREFIX):
            return None
        return self._rpc("playbook_source_get", {"p_company": company_id, "p_source_id": source_id}) or None

    def get_import(self, company_id, import_id) -> Optional[dict]:
        return self._rpc("playbook_import_get", {"p_company": company_id, "p_import": import_id}) or None

    def save_import(self, company_id, record, key) -> None:
        if not key or record.get("status") != "ready" or record.get("published"):
            return
        draft = record.get("draft") or {}
        self._rpc(
            "save_playbook_draft",
            {
                "p_company": company_id,
                "p_motion": key,
                "p_import": record["import_id"],
                "p_payload": draft.get("text") or "",
                "p_contradictions": draft.get("contradictions") or [],
            },
        )

    # -- company knowledge

    def get_knowledge(self, company_id: str) -> Optional[dict]:
        return _knowledge_view(self._rpc("company_knowledge_get", {"p_company": company_id}))

    def save_knowledge(self, company_id, data, *, base_updated_at=None) -> dict:
        base = None
        if base_updated_at:
            parsed = parse_ts(base_updated_at)
            if parsed is None:
                raise StaleKnowledgeError()
            base = parsed.isoformat()
        row = self._rpc(
            "company_knowledge_save",
            {
                "p_company": company_id,
                "p_data": normalize_knowledge(data),
                "p_source_id": None,
                "p_base_updated_at": base,
            },
        )
        return _knowledge_view(row)  # type: ignore[return-value]

    # -- intake

    def save_intake(self, company_id, types, knowledge, source_id) -> dict:
        items = []
        for item in types:
            payload = {
                "key": item.get("key"),
                "steps": item.get("steps"),
                "entries": item.get("entries"),
                "qualification": item.get("qualification"),
                "text": _intake_text(item),
            }
            ensure = item.get("ensure")
            if ensure:
                meta = self._meta(ensure.get("label", UNSET), ensure.get("applies_to", UNSET))
                payload["ensure"] = {"name": ensure.get("name") or item.get("key"), "meta": meta}
            items.append(payload)
        result = self._rpc(
            "playbook_intake_save",
            {
                "p_company": company_id,
                "p_types": items,
                "p_knowledge": normalize_knowledge(knowledge) if knowledge is not None else None,
                "p_source_id": source_id,
            },
        ) or {}
        return {"types": list(result.get("types") or []), "knowledge": _knowledge_view(result.get("knowledge"))}


# ─── memory ───────────────────────────────────────────────────────────────────────────────────


class InMemoryPlaybookRepository:
    """TEST FAKE of the playbooks storage: the same operations with the same semantics as the SQL functions of
    migration 066_playbooks_v2, over dicts. Not for production (state lives in the process). It exists so the API
    tests run without a database; the repository contract suite runs its scenarios against this and against real
    PostgreSQL, which keeps the two honest.

    `seed` = {company_id: {key: status}} with status published | paused | draft | missing, for tests that need a
    company that already has playbooks (a published/paused one gets an empty published version).

    Intake atomicity: a failing item restores the state from before the call (the SQL function gets it from its
    transaction).
    """

    def __init__(self, seed: Optional[dict] = None):
        self._playbooks: dict[tuple[str, str], dict] = {}
        self._types: dict[tuple[str, str], dict] = {}
        self._versions: dict[str, dict] = {}
        self._imports: dict[str, dict] = {}
        self._knowledge: dict[str, dict] = {}
        self._clock: Optional[datetime] = None
        for company_id, statuses in (seed or {}).items():
            for key, status in statuses.items():
                self._seed(company_id, key, status)

    # -- internals

    def _tick(self) -> datetime:
        """Now, strictly later than every stamp handed out before (by more than the millisecond stale checks
        compare at), like the SQL trigger."""
        now = datetime.now(timezone.utc)
        if self._clock is not None and now < self._clock + timedelta(milliseconds=2):
            now = self._clock + timedelta(milliseconds=2)
        self._clock = now
        return now

    def _stamp(self) -> str:
        return self._tick().isoformat()

    def _seed(self, company_id: str, key: str, status: str) -> None:
        if status == "missing":
            self._types[(company_id, key)] = {"name": key, "active": True}
            return
        pb = self._ensure_playbook(company_id, key)
        version = self._new_version(pb, "published" if status in ("published", "paused") else "draft", [], [], [])
        if status in ("published", "paused"):
            pb["active_version_id"] = version["id"]
        if status == "paused":
            pb["state"] = "paused"

    def _ensure_playbook(self, company_id: str, key: str) -> dict:
        slot = (company_id, key)
        if slot not in self._playbooks:
            self._playbooks[slot] = {
                "id": str(uuid.uuid4()), "company_id": company_id, "key": key, "active_version_id": None,
                "label": None, "applies_to": None, "state": "active", "archived_at": None,
            }
        return self._playbooks[slot]

    def _new_version(self, pb: dict, status: str, steps: list, entries: list, qualification: list) -> dict:
        stamp = self._stamp()
        version = {
            "id": str(uuid.uuid4()), "playbook_id": pb["id"], "status": status, "steps": copy.deepcopy(steps),
            "entries": copy.deepcopy(entries), "qualification": copy.deepcopy(qualification),
            "created_at": stamp, "updated_at": stamp,
        }
        self._versions[version["id"]] = version
        return version

    def _touch(self, version: dict) -> None:
        version["updated_at"] = self._stamp()

    def _versions_of(self, pb: dict) -> list[dict]:
        return [v for v in self._versions.values() if v["playbook_id"] == pb["id"]]

    def _pending(self, pb: dict) -> Optional[dict]:
        """The latest draft, when it is newer than the published version (or nothing is published)."""
        live = self._versions.get(pb["active_version_id"]) if pb["active_version_id"] else None
        drafts = [v for v in self._versions_of(pb) if v["status"] == "draft"]
        if live is not None:
            drafts = [v for v in drafts if parse_ts(v["created_at"]) > parse_ts(live["created_at"])]
        return max(drafts, key=lambda v: parse_ts(v["created_at"])) if drafts else None

    def _status(self, pb: dict) -> str:
        if pb["active_version_id"] and pb["state"] == "paused":
            return "paused"
        if pb["active_version_id"]:
            return "published"
        if any(v["status"] == "draft" for v in self._versions_of(pb)):
            return "draft"
        return "missing"

    def _listed(self, company_id: str) -> dict[str, dict]:
        """key -> {"pb": playbook row | None} for the types the company lists (not deleted)."""
        out: dict[str, dict] = {}
        for (company, key), pb in self._playbooks.items():
            if company == company_id and not pb["archived_at"]:
                out[key] = {"pb": pb}
        for (company, key), row in self._types.items():
            if company == company_id and row["active"] and (company, key) not in self._playbooks:
                out[key] = {"pb": None}
        return out

    def _unarchive(self, pb: dict) -> None:
        if pb["archived_at"]:
            pb["archived_at"], pb["active_version_id"], pb["state"] = None, None, "active"

    def _valid_source(self, company_id: str, source_id: Optional[str]) -> Optional[str]:
        return source_id if self.get_source(company_id, source_id) else None

    def _import_row(self, import_id: str, company_id: str, pb: Optional[dict], kind: str, draft: dict) -> None:
        self._imports[import_id] = {
            "id": import_id, "company_id": company_id, "playbook_id": pb["id"] if pb else None, "kind": kind,
            "status": "ready", "draft": draft, "active_version_id": pb["active_version_id"] if pb else None,
            "created_at": self._stamp(),
        }

    # -- the list and the editor

    def list_types(self, company_id: str, *, include_draft: bool = True) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for key, entry in sorted(self._listed(company_id).items()):
            pb = entry["pb"]
            if pb is None:
                out[key] = {"status": "missing", "label": None, "applies_to": None,
                            **summarize(None, has_draft=False, paused=False)}
                continue
            status = self._status(pb)
            pending = self._pending(pb) if include_draft else None
            shown = pending or (self._versions.get(pb["active_version_id"]) if pb["active_version_id"] else None)
            out[key] = {
                "status": status,
                "label": pb["label"] or None,
                "applies_to": copy.deepcopy(pb["applies_to"]),
                **summarize(shown, has_draft=pending is not None, paused=status == "paused"),
            }
        return out

    def editor_snapshot(self, company_id: str, key: str, *, include_draft: bool) -> dict:
        pb = self._playbooks.get((company_id, key))
        if pb is None or pb["archived_at"]:
            return {"state": "empty", "version": None, "has_live": False, "source": None, "paused": False}
        live = self._versions.get(pb["active_version_id"]) if pb["active_version_id"] else None
        pending = self._pending(pb) if include_draft else None
        state, shown = "empty", None
        if pending is not None:
            state, shown = "draft", pending
        elif live is not None:
            state, shown = "published", live
        source = None
        if shown is not None:
            recorded = (self._imports.get(f"editor:{shown['id']}", {}).get("draft") or {}).get("source_id")
            source = self.get_source(company_id, recorded)
        return {
            "state": state,
            "version": _version_view(copy.deepcopy(shown)),
            "has_live": live is not None,
            "source": source,
            "paused": live is not None and pb["state"] == "paused",
        }

    # -- drafts and publishing

    def save_draft(
        self, company_id, key, steps, entries, *, qualification=None, source_id=None, base_updated_at=None,
    ) -> dict:
        base = _base_iso(base_updated_at)
        pb = self._ensure_playbook(company_id, key)
        self._unarchive(pb)
        src = self._valid_source(company_id, source_id)
        live = self._versions.get(pb["active_version_id"]) if pb["active_version_id"] else None
        pending = self._pending(pb)
        if pending is not None:
            if base and not same_instant(base, pending["updated_at"]):
                raise StaleDraftError()
            pending["steps"], pending["entries"] = copy.deepcopy(steps), copy.deepcopy(entries)
            if qualification is not None:
                pending["qualification"] = copy.deepcopy(qualification)
            self._touch(pending)
            version = pending
        else:
            if base and not (live and same_instant(base, live["updated_at"])):
                raise StaleDraftError()
            carried = qualification if qualification is not None else list((live or {}).get("qualification") or [])
            version = self._new_version(pb, "draft", steps, entries, carried)
        import_id = f"editor:{version['id']}"
        existing = self._imports.get(import_id)
        effective = src or ((existing or {}).get("draft") or {}).get("source_id")
        if not effective and existing is None and live is not None:
            effective = ((self._imports.get(f"editor:{live['id']}") or {}).get("draft") or {}).get("source_id")
        draft = {
            "text": render_text(steps, entries, qualification or []),
            "source_ref": "editor",
            "contradictions": [],
            "version_id": version["id"],
        }
        if effective:
            draft["source_id"] = effective
        self._import_row(import_id, company_id, pb, "editor", draft)
        return _version_view(copy.deepcopy(version))  # type: ignore[return-value]

    def discard_draft(self, company_id: str, key: str) -> bool:
        pb = self._playbooks.get((company_id, key))
        if pb is None:
            return False
        live = self._versions.get(pb["active_version_id"]) if pb["active_version_id"] else None
        doomed = [
            v for v in self._versions_of(pb)
            if v["status"] == "draft" and (live is None or parse_ts(v["created_at"]) > parse_ts(live["created_at"]))
        ]
        if not doomed:
            return False
        for version in doomed:
            self._imports.pop(f"editor:{version['id']}", None)
            del self._versions[version["id"]]
        return True

    def publish(self, company_id: str, key: str) -> str:
        pb = self._playbooks.get((company_id, key))
        if pb is None or pb["archived_at"]:
            raise PublishError("not_a_draft")
        imports = [i for i in self._imports.values() if i["playbook_id"] == pb["id"]]
        if imports:
            latest = max(imports, key=lambda i: parse_ts(i["created_at"]))
            if (latest.get("draft") or {}).get("contradictions"):
                raise PublishError("contradiction")
        pending = self._pending(pb)
        if pending is None:
            raise PublishError("not_a_draft")
        pending["status"] = "published"
        self._touch(pending)
        pb["active_version_id"], pb["state"], pb["archived_at"] = pending["id"], "active", None
        return pending["id"]

    def set_state(self, company_id: str, key: str, action: str) -> None:
        if action not in LIFECYCLE_ACTIONS:
            raise PlaybookRepositoryError("invalid_action")
        slot = (company_id, key)
        pb = self._playbooks.get(slot)
        kind = self._types.get(slot)
        if action == "pause":
            if pb is None or pb["archived_at"] or not pb["active_version_id"] or pb["state"] != "active":
                raise LifecycleError("not_published")
            pb["state"] = "paused"
        elif action == "resume":
            if pb is None or pb["archived_at"] or not pb["active_version_id"] or pb["state"] != "paused":
                raise LifecycleError("not_paused")
            pb["state"] = "active"
        elif action == "archive":
            if pb is not None and not pb["archived_at"]:
                for version in [v for v in self._versions_of(pb) if v["status"] == "draft"]:
                    self._imports.pop(f"editor:{version['id']}", None)
                    del self._versions[version["id"]]
                pb["archived_at"] = self._stamp()
            elif pb is not None or not (kind and kind["active"]):
                raise LifecycleError("not_found")
            if kind:
                kind["active"] = False
        else:
            if pb is not None:
                if not pb["archived_at"]:
                    raise LifecycleError("not_archived")
                pb["archived_at"] = None
            elif not (kind and not kind["active"]):
                raise LifecycleError("not_archived")
            if kind:
                kind["active"] = True

    # -- types, names and rules

    def add_type(self, company_id, key, name, *, label=UNSET, applies_to=UNSET) -> None:
        cleaned = (key or "").strip()
        if not cleaned:
            raise PublishError("empty_type")
        slot = (company_id, cleaned)
        row = self._types.get(slot)
        if row is None:
            self._types[slot] = {"name": (name or "").strip() or cleaned, "active": True}
        else:
            row["active"] = True
        if slot in self._playbooks:
            self._unarchive(self._playbooks[slot])
        self.set_meta(company_id, cleaned, label=label, applies_to=applies_to)

    def set_meta(self, company_id, key, *, label=UNSET, applies_to=UNSET) -> None:
        if label is UNSET and applies_to is UNSET:
            return
        pb = self._ensure_playbook(company_id, key)
        if label is not UNSET:
            pb["label"] = label or None
        if applies_to is not UNSET:
            pb["applies_to"] = copy.deepcopy(applies_to)

    # -- sources and imports

    def save_source(self, company_id, key, kind, name, text) -> dict:
        pb = self._ensure_playbook(company_id, key) if key is not None else None
        source_id = f"{SOURCE_PREFIX}{uuid.uuid4()}"
        self._import_row(
            source_id, company_id, pb, kind,
            {"text": text, "name": name or "", "source_ref": f"{kind}:{source_id}"},
        )
        return {"id": source_id, "kind": kind, "name": name or ""}

    def get_source(self, company_id, source_id) -> Optional[dict]:
        if not source_id or not str(source_id).startswith(SOURCE_PREFIX):
            return None
        row = self._imports.get(source_id)
        if not row or row["company_id"] != company_id:
            return None
        return {"id": source_id, "kind": row["kind"], "name": str((row.get("draft") or {}).get("name") or "")}

    def get_import(self, company_id, import_id) -> Optional[dict]:
        row = self._imports.get(import_id)
        if not row or row["company_id"] != company_id:
            return None
        return {
            "id": row["id"], "import_id": row["id"], "kind": row["kind"], "status": row["status"],
            "draft": copy.deepcopy(row["draft"]),
            "active_version_id": row["active_version_id"], "published": False,
        }

    def save_import(self, company_id, record, key) -> None:
        if not key or record.get("status") != "ready" or record.get("published"):
            return
        pb = self._ensure_playbook(company_id, key)
        self._unarchive(pb)
        import_id = record["import_id"]
        if import_id in self._imports:
            return
        draft = record.get("draft") or {}
        text = draft.get("text") or ""
        version = self._new_version(
            pb, "draft",
            [{"step_id": "imported", "label": text[:80], "criterion": text}],
            [{"entry_id": f"text:{import_id}", "category": "process", "guidance": text, "source_ref": f"text:{import_id}"}],
            [],
        )
        del version
        self._import_row(
            import_id, company_id, pb, "text",
            {"text": text, "source_ref": f"text:{import_id}", "contradictions": list(draft.get("contradictions") or [])},
        )

    # -- company knowledge

    def get_knowledge(self, company_id: str) -> Optional[dict]:
        return _knowledge_view(copy.deepcopy(self._knowledge.get(company_id)))

    def _write_knowledge(
        self, company_id: str, data: dict, source_id: Optional[str], base_updated_at: Optional[str],
    ) -> dict:
        row = self._knowledge.get(company_id)
        if base_updated_at:
            base = parse_ts(base_updated_at)
            if base is None or not (row and same_instant(base, row["updated_at"])):
                raise StaleKnowledgeError()
        self._knowledge[company_id] = {
            "data": normalize_knowledge(data),
            "source_id": source_id if source_id is not None else (row or {}).get("source_id"),
            "updated_at": self._stamp(),
        }
        return _knowledge_view(copy.deepcopy(self._knowledge[company_id]))  # type: ignore[return-value]

    def save_knowledge(self, company_id, data, *, base_updated_at=None) -> dict:
        return self._write_knowledge(company_id, data, None, base_updated_at)

    # -- intake

    def save_intake(self, company_id, types, knowledge, source_id) -> dict:
        before = copy.deepcopy(
            (self._playbooks, self._types, self._versions, self._imports, self._knowledge, self._clock)
        )
        try:
            saved = []
            for item in types:
                if (
                    not isinstance(item, dict)
                    or not str(item.get("key") or "").strip()
                    or not isinstance(item.get("steps"), list)
                    or not isinstance(item.get("entries"), list)
                ):
                    raise PlaybookRepositoryError("invalid_type_item")
                key = item["key"]
                ensure = item.get("ensure")
                if ensure and key not in self._listed(company_id):
                    self.add_type(
                        company_id, key, ensure.get("name") or key,
                        label=ensure.get("label", UNSET), applies_to=ensure.get("applies_to", UNSET),
                    )
                version = self.save_draft(
                    company_id, key, item["steps"], item["entries"],
                    qualification=item.get("qualification"), source_id=source_id,
                )
                saved.append({"sales_motion_key": key, "version_id": version["id"]})
            row = self._write_knowledge(company_id, knowledge, source_id, None) if knowledge is not None else None
        except Exception:
            (self._playbooks, self._types, self._versions, self._imports, self._knowledge, self._clock) = before
            raise
        return {"types": saved, "knowledge": row}


# ─── which repository the app uses ─────────────────────────────────────────────────────────────

_current: Optional[PlaybookRepository] = None
_default_memory = InMemoryPlaybookRepository()


def set_playbook_repository(repository: Optional[PlaybookRepository]) -> None:
    """Startup installs the SQL repository; a test installs its own. None goes back to a FRESH in-memory repository
    (the default when nothing was installed), so a test that resets it starts clean."""
    global _current, _default_memory
    _current = repository
    if repository is None:
        _default_memory = InMemoryPlaybookRepository()


def get_playbook_repository() -> PlaybookRepository:
    return _current if _current is not None else _default_memory
