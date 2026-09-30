"""Playbook state. Memory is the test default. Postgres is what startup installs."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.services.playbooks.knowledge import StaleKnowledgeError, normalize_knowledge
from app.services.playbooks.structured import editor_view
from app.services.playbooks.versions import (
    LifecycleError,
    PublishError,
    StaleDraftError,
    accept_publish,
    is_newer,
    parse_ts,
    same_instant,
)

logger = logging.getLogger(__name__)

SOURCE_PREFIX = "source:"
_VERSION_COLS = "id,status,steps,entries,qualification,created_at,updated_at"
_KNOWLEDGE_COLS = "data,source_id,updated_at"


def _stamp(previous: str | None = None) -> str:
    """Now as ISO. Strictly later (by a whole millisecond, the resolution stale-draft checks
    compare at) than `previous`, so two quick saves never share a timestamp."""
    now = datetime.now(timezone.utc)
    before = parse_ts(previous)
    if before is not None and now < before + timedelta(milliseconds=1):
        now = before + timedelta(milliseconds=2)
    return now.isoformat()


def _source_view(record: dict | None, source_id: str) -> dict | None:
    if not record:
        return None
    draft = record.get("draft") or {}
    return {"id": source_id, "kind": record.get("kind"), "name": str(draft.get("name") or "")}

_UNSET = object()

NO_VERSION_SUMMARY = {"step_count": 0, "answer_count": 0, "criteria_count": 0, "has_draft": False, "paused": False}


def _summary(version: dict | None, *, has_draft: bool, paused: bool = False) -> dict:
    """What the list shows of a playbook: how many steps, objection answers and qualification
    criteria the version the editor opens has (counted the way the editor shows them), whether
    a pending draft exists and whether the playbook is paused (then the counts come from the
    paused version when there is no draft)."""
    view = editor_view(version)
    return {
        "step_count": len(view["steps"]),
        "answer_count": len(view["objections"]),
        "criteria_count": len(view["qualification"]),
        "has_draft": has_draft,
        "paused": paused,
    }



class MemoryPlaybookStore:
    def __init__(
        self,
        motions: dict,
        imports: dict,
        latest: dict | None = None,
        activated: dict | None = None,
        structured: dict | None = None,
        published_versions: dict | None = None,
        details: dict | None = None,
        knowledge: dict | None = None,
        lifecycle: dict | None = None,
    ):
        self._motions = motions
        self._imports = imports
        self._latest = latest if latest is not None else {}
        self._activated = activated if activated is not None else {}
        # The API builds a new instance per request: shared dicts keep editor drafts alive.
        self._structured = structured if structured is not None else {}
        self._published_versions = published_versions if published_versions is not None else {}
        # (company_id, key) -> {"label", "applies_to"}: the type's name and routing rule (T7).
        self._details = details if details is not None else {}
        # company_id -> {"data", "source_id", "updated_at"}: what Vocify knows about the company.
        self._knowledge = knowledge if knowledge is not None else {}
        # (company_id, key) -> {"paused": {"version", "version_id"} | None, "archived_at", "archived_state"}:
        # the memory twin of playbooks.paused_version_id / archived_at / archived_state.
        self._lifecycle = lifecycle if lifecycle is not None else {}

    def _archived(self, slot: tuple) -> bool:
        return bool((self._lifecycle.get(slot) or {}).get("archived_at"))

    def _paused(self, slot: tuple) -> dict | None:
        """{"version", "version_id"} of the paused version, None when the type is not paused
        (a deleted one is not "paused": it is gone)."""
        life = self._lifecycle.get(slot) or {}
        return None if life.get("archived_at") else life.get("paused")

    def _unarchive(self, company_id: str, key: str) -> None:
        """A deleted type that is written to again comes back empty: no old version, no old draft."""
        slot = (company_id, key)
        if self._archived(slot):
            self._lifecycle.pop(slot, None)
            self._motions.setdefault(company_id, {})[key] = "missing"

    def get_import(self, company_id: str, import_id: str):
        record = self._imports.get(import_id)
        if not record or record.get("company_id") != company_id:
            return None
        return record

    def save_import(self, company_id: str, record: dict, sales_motion_key: str | None) -> None:
        self._imports[record["import_id"]] = {**record, "company_id": company_id}
        if sales_motion_key and record.get("status") == "ready" and not record.get("published"):
            self._unarchive(company_id, sales_motion_key)
            company = self._motions.setdefault(company_id, {})
            if company.get(sales_motion_key) not in ("published", "paused"):
                company[sales_motion_key] = "draft"
        if sales_motion_key and record.get("status") == "ready":
            self._latest[(company_id, sales_motion_key)] = record

    def save_source(self, company_id: str, key: str | None, kind: str, name: str | None, text: str) -> dict:
        """Keeps the original material a playbook was structured from. Creates no version.
        `key` None = a document for the whole company (not tied to one call type)."""
        del key  # the memory double has no playbook row to attach it to
        source_id = f"{SOURCE_PREFIX}{uuid.uuid4()}"
        self._imports[source_id] = {
            "id": source_id,
            "import_id": source_id,
            "company_id": company_id,
            "kind": kind,
            "status": "ready",
            "draft": {"text": text, "name": name or "", "source_ref": f"{kind}:{source_id}"},
            "active_version_id": None,
            "published": False,
        }
        return {"id": source_id, "kind": kind, "name": name or ""}

    def get_source(self, company_id: str, source_id: str | None) -> dict | None:
        if not source_id or not str(source_id).startswith(SOURCE_PREFIX):
            return None
        record = self._imports.get(source_id)
        if not record or record.get("company_id") != company_id:
            return None
        return _source_view(record, source_id)

    def motions(self, company_id: str) -> dict:
        return {
            key: status
            for key, status in (self._motions.get(company_id) or {}).items()
            if not self._archived((company_id, key))
        }

    def save_structured_draft(
        self,
        company_id: str,
        key: str,
        steps: list,
        entries: list,
        *,
        base_updated_at: str | None = None,
        source_id: str | None = None,
        qualification: list | None = None,
    ) -> dict:
        """Test double of SupabasePlaybookStore.save_structured_draft: a pending draft is
        updated in place (same id), otherwise a new one is created. `qualification` None
        leaves the draft's criteria as they are (a new draft starts from the live version's)."""
        slot = (company_id, key)
        self._unarchive(company_id, key)
        pending = self._structured.get(slot)
        # A paused playbook's version is what a new draft is written over, as if it were live.
        live = self._published_versions.get(slot) or (self._paused(slot) or {}).get("version")
        if source_id is not None and not self.get_source(company_id, source_id):
            source_id = None
        if pending is not None:
            if base_updated_at and not same_instant(base_updated_at, pending.get("updated_at")):
                raise StaleDraftError()
            pending["steps"] = steps
            pending["entries"] = entries
            if qualification is not None:
                pending["qualification"] = qualification
            pending["updated_at"] = _stamp(pending.get("updated_at"))
            if source_id is not None:
                pending["source_id"] = source_id
            version = pending
        else:
            if base_updated_at and not (live and same_instant(base_updated_at, live.get("updated_at"))):
                raise StaleDraftError()
            stamp = _stamp()
            version = {
                "id": str(uuid.uuid4()),
                "status": "draft",
                "steps": steps,
                "entries": entries,
                "qualification": qualification if qualification is not None else list((live or {}).get("qualification") or []),
                "created_at": stamp,
                "updated_at": stamp,
                "source_id": source_id if source_id is not None else (live or {}).get("source_id"),
            }
            self._structured[slot] = version
        company = self._motions.setdefault(company_id, {})
        if company.get(key) not in ("published", "paused"):
            company[key] = "draft"
        self._latest[slot] = {"draft": {"contradictions": []}}
        return dict(version)

    def editor_snapshot(self, company_id: str, key: str, *, include_draft: bool) -> dict:
        """{state, version, has_live, source, paused}: state is "draft" (the pending draft, only
        for editors), "published" (the live version, or the paused one of a paused playbook) or
        "empty" (also for a deleted type)."""
        slot = (company_id, key)
        if self._archived(slot):
            return {"state": "empty", "version": None, "has_live": False, "source": None, "paused": False}
        draft = self._structured.get(slot)
        live = self._published_versions.get(slot)
        paused = self._paused(slot)
        under = live or (paused or {}).get("version")
        if include_draft and draft and draft.get("status") == "draft":
            state, version = "draft", draft
        elif under:
            state, version = "published", under
        else:
            state, version = "empty", None
        return {
            "state": state,
            "version": dict(version) if version else None,
            "has_live": under is not None,
            "source": self.get_source(company_id, (version or {}).get("source_id")),
            "paused": paused is not None,
        }

    def editor_version(self, company_id: str, key: str, *, include_draft: bool) -> tuple[str, dict | None]:
        snapshot = self.editor_snapshot(company_id, key, include_draft=include_draft)
        return snapshot["state"], snapshot["version"]

    def discard_draft(self, company_id: str, key: str) -> bool:
        """Removes the pending draft. A published version is never touched."""
        slot = (company_id, key)
        removed = self._structured.pop(slot, None)
        if removed is None:
            return False
        self._latest.pop(slot, None)
        company = self._motions.setdefault(company_id, {})
        if company.get(key) not in ("published", "paused"):
            company[key] = "missing"
        return True

    def publish(self, company_id: str, key: str, role: str) -> dict:
        latest = self._latest.get((company_id, key)) or {}
        if (latest.get("draft") or {}).get("contradictions"):
            raise PublishError("contradiction")
        updated = accept_publish(self.motions(company_id), key, role)
        if self._motions.get(company_id, {}).get(key) == "paused" and (company_id, key) not in self._structured:
            raise PublishError("not_a_draft")  # a paused playbook is published again only by a draft
        self._motions.setdefault(company_id, {})[key] = "published"
        self._lifecycle.pop((company_id, key), None)  # publishing lifts the pause
        draft = self._structured.pop((company_id, key), None)
        version_id = (draft or {}).get("id") or str(uuid.uuid4())
        if draft:
            self._published_versions[(company_id, key)] = {
                **draft,
                "status": "published",
                "updated_at": _stamp(draft.get("updated_at")),
            }
        self._activated[(company_id, key)] = version_id
        return updated

    def activated(self, company_id: str) -> dict:
        return {
            key: version
            for (company, key), version in self._activated.items()
            if company == company_id
        }

    def add_type(self, company_id: str, key: str, name: str, role: str) -> dict:
        from app.services.playbooks.versions import can_publish

        if not can_publish(role):
            raise PublishError("forbidden")
        cleaned = (key or "").strip()
        if not cleaned:
            raise PublishError("empty_type")
        self._unarchive(company_id, cleaned)
        company = self._motions.setdefault(company_id, {})
        company.setdefault(cleaned, "missing")
        del name
        return self.motions(company_id)

    def details(self, company_id: str) -> dict:
        """key -> {"label", "applies_to"} as saved for the company (T7)."""
        return {
            key: dict(meta)
            for (company, key), meta in self._details.items()
            if company == company_id and not self._archived((company, key))
        }

    def version_summaries(self, company_id: str, *, include_draft: bool = True) -> dict:
        """key -> {step_count, answer_count, criteria_count, has_draft, paused} for every type
        that has a version: the pending draft (managers) else the live version, else the paused
        one. A deleted type has none."""
        out: dict = {}
        keys = {
            key
            for (company, key) in list(self._structured) + list(self._published_versions) + list(self._lifecycle)
            if company == company_id
        }
        for key in keys:
            slot = (company_id, key)
            if self._archived(slot):
                continue
            draft = self._structured.get(slot)
            if draft is not None and draft.get("status") != "draft":
                draft = None
            paused = self._paused(slot)
            live = self._published_versions.get(slot) or (paused or {}).get("version")
            shown = draft if (include_draft and draft is not None) else live
            out[key] = _summary(shown, has_draft=include_draft and draft is not None, paused=paused is not None)
        return out

    # -- pause, resume, delete (docs/superpowers/plans/2026-09-29-playbooks-v2.md, section 16) --

    def _park(self, slot: tuple) -> None:
        """The active version becomes the paused one."""
        version = self._published_versions.pop(slot, None)
        version_id = self._activated.pop(slot, None) or (version or {}).get("id")
        life = self._lifecycle.setdefault(slot, {"paused": None, "archived_at": None, "archived_state": None})
        life["paused"] = {"version": version, "version_id": version_id}

    def _unpark(self, slot: tuple) -> None:
        """The paused version is the active one again."""
        life = self._lifecycle.get(slot) or {}
        paused = life.get("paused")
        if not paused:
            return
        if paused.get("version") is not None:
            self._published_versions[slot] = paused["version"]
        if paused.get("version_id"):
            self._activated[slot] = paused["version_id"]
        life["paused"] = None
        if not life.get("archived_at"):
            self._lifecycle.pop(slot, None)

    def pause(self, company_id: str, key: str) -> dict:
        """Published -> paused: new calls stop being evaluated with it, the content stays.
        LifecycleError("not_published") when it is anything else."""
        slot = (company_id, key)
        if self._archived(slot) or self._motions.get(company_id, {}).get(key) != "published":
            raise LifecycleError("not_published")
        self._park(slot)
        self._motions[company_id][key] = "paused"
        return self.motions(company_id)

    def resume(self, company_id: str, key: str) -> dict:
        """Paused -> published again. LifecycleError("not_paused") when it is not paused."""
        slot = (company_id, key)
        if self._paused(slot) is None or self._motions.get(company_id, {}).get(key) != "paused":
            raise LifecycleError("not_paused")
        self._unpark(slot)
        self._motions[company_id][key] = "published"
        return self.motions(company_id)

    def archive(self, company_id: str, key: str) -> dict:
        """"Eliminar": the type leaves the list. The status it had is kept (archived_state) to
        undo it, the active version is parked, the pending draft is deleted. LifecycleError
        ("not_found") when the company has no such type."""
        slot = (company_id, key)
        company = self._motions.get(company_id, {})
        if key not in company or self._archived(slot):
            raise LifecycleError("not_found")
        before = company[key]
        if before == "published":
            self._park(slot)
        self._structured.pop(slot, None)
        self._latest.pop(slot, None)
        life = self._lifecycle.setdefault(slot, {"paused": None, "archived_at": None, "archived_state": None})
        life["archived_at"] = _stamp()
        life["archived_state"] = before
        company[key] = "paused" if life.get("paused") else "missing"
        return self.motions(company_id)

    def restore(self, company_id: str, key: str) -> dict:
        """Undo "Eliminar": back to the status before it (published -> published again; paused
        stays paused; a draft is gone, so it is empty). LifecycleError("not_archived")."""
        slot = (company_id, key)
        life = self._lifecycle.get(slot) or {}
        if not life.get("archived_at"):
            raise LifecycleError("not_archived")
        before = life.get("archived_state")
        life["archived_at"], life["archived_state"] = None, None
        company = self._motions.setdefault(company_id, {})
        if before == "published" and life.get("paused"):
            self._unpark(slot)
            company[key] = "published"
        elif life.get("paused"):
            company[key] = "paused"
        else:
            company[key] = "missing"
        if not life.get("paused"):
            self._lifecycle.pop(slot, None)
        return self.motions(company_id)

    def get_knowledge(self, company_id: str) -> dict | None:
        """{data, source_id, updated_at} of what Vocify knows about the company, None when
        nothing was ever saved."""
        row = self._knowledge.get(company_id)
        return {**row, "data": normalize_knowledge(row["data"])} if row else None

    def save_knowledge(
        self, company_id: str, data: dict, *, base_updated_at: str | None = None, source_id=_UNSET,
    ) -> dict:
        """Replaces the company's knowledge (no draft: it takes effect at once). With
        `base_updated_at`, StaleKnowledgeError when it is not the saved row's updated_at."""
        row = self._knowledge.get(company_id)
        if base_updated_at and not (row and same_instant(base_updated_at, row.get("updated_at"))):
            raise StaleKnowledgeError()
        saved = {
            "data": normalize_knowledge(data),
            "source_id": (row or {}).get("source_id") if source_id is _UNSET else source_id,
            "updated_at": _stamp((row or {}).get("updated_at")),
        }
        self._knowledge[company_id] = saved
        return dict(saved)

    def save_type_meta(self, company_id: str, key: str, *, label=_UNSET, applies_to=_UNSET) -> None:
        """Saves a type's label and/or routing rule. The type shows up in motions()."""
        self._motions.setdefault(company_id, {}).setdefault(key, "missing")
        meta = self._details.setdefault((company_id, key), {"label": None, "applies_to": None})
        if label is not _UNSET:
            meta["label"] = label
        if applies_to is not _UNSET:
            meta["applies_to"] = applies_to


class SupabasePlaybookStore:
    def __init__(self, supabase):
        self.supabase = supabase
        self._activated: dict[tuple[str, str], str] = {}

    def get_import(self, company_id: str, import_id: str):
        result = (
            self.supabase.table("playbook_imports")
            .select("id,status,draft,active_version_id")
            .eq("id", import_id)
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        rows = list(getattr(result, "data", None) or [])
        if not rows:
            return None
        row = rows[0]
        return {
            "id": row.get("id"),
            "import_id": row.get("id"),
            "status": row.get("status"),
            "draft": row.get("draft"),
            "active_version_id": row.get("active_version_id"),
            "published": False,
        }

    def save_import(self, company_id: str, record: dict, sales_motion_key: str | None) -> None:
        if not sales_motion_key or record.get("status") != "ready" or record.get("published"):
            return
        archived = self._playbook(company_id, sales_motion_key, create=False)
        if archived and archived.get("archived_at"):
            self._unarchive(archived)  # a deleted type written to again comes back empty
        text = ((record.get("draft") or {}).get("text")) or ""
        self.supabase.rpc(
            "save_playbook_draft",
            {
                "p_company": company_id,
                "p_motion": sales_motion_key,
                "p_import": record["import_id"],
                "p_payload": text,
                "p_contradictions": (record.get("draft") or {}).get("contradictions") or [],
            },
        ).execute()

    def _playbook(self, company_id: str, key: str, *, create: bool) -> dict | None:
        if create:
            self.supabase.table("playbooks").upsert(
                {"company_id": company_id, "sales_motion_key": key},
                on_conflict="company_id,sales_motion_key",
                ignore_duplicates=True,
            ).execute()
        rows = (
            self.supabase.table("playbooks")
            .select("id,active_version_id,paused_version_id,archived_at,archived_state")
            .eq("company_id", company_id)
            .eq("sales_motion_key", key)
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def _unarchive(self, playbook: dict) -> dict:
        """A deleted type that is written to again comes back empty: the old version is not
        resurrected (it stays as a row nothing points at) and the old drafts are already gone."""
        cleared = {"archived_at": None, "paused_version_id": None, "archived_state": None}
        self.supabase.table("playbooks").update(cleared).eq("id", playbook["id"]).execute()
        return {**playbook, **cleared}

    def save_source(self, company_id: str, key: str | None, kind: str, name: str | None, text: str) -> dict:
        """Keeps the original material a playbook was structured from (playbook_imports,
        id `source:{uuid}`). Creates no version. `key` None = a document for the whole
        company: the row has no playbook (and no playbook row is created for it, which
        would list a phantom call type)."""
        playbook = None
        if key is not None:
            playbook = self._playbook(company_id, key, create=True)
            if not playbook:
                raise RuntimeError("playbook row missing after upsert")
        source_id = f"{SOURCE_PREFIX}{uuid.uuid4()}"
        self.supabase.table("playbook_imports").insert({
            "id": source_id,
            "company_id": company_id,
            "playbook_id": playbook["id"] if playbook else None,
            "kind": kind,
            "status": "ready",
            "draft": {"text": text, "name": name or "", "source_ref": f"{kind}:{source_id}"},
            "active_version_id": playbook.get("active_version_id") if playbook else None,
        }).execute()
        return {"id": source_id, "kind": kind, "name": name or ""}

    def get_source(self, company_id: str, source_id: str | None) -> dict | None:
        if not source_id or not str(source_id).startswith(SOURCE_PREFIX):
            return None
        rows = (
            self.supabase.table("playbook_imports")
            .select("id,kind,draft")
            .eq("id", source_id)
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        ).data or []
        return _source_view(rows[0], source_id) if rows else None

    def _version_row(self, version_id: str | None) -> dict | None:
        if not version_id:
            return None
        rows = (
            self.supabase.table("playbook_versions")
            .select(_VERSION_COLS)
            .eq("id", version_id)
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def _live_version(self, playbook: dict) -> dict | None:
        return self._version_row(playbook.get("active_version_id"))

    @staticmethod
    def _is_paused(playbook: dict) -> bool:
        return (
            not playbook.get("active_version_id")
            and bool(playbook.get("paused_version_id"))
            and not playbook.get("archived_at")
        )

    def _paused_version(self, playbook: dict) -> dict | None:
        return self._version_row(playbook.get("paused_version_id")) if self._is_paused(playbook) else None

    def _shown_under_draft(self, playbook: dict) -> dict | None:
        """The version a draft is written over and compared with: the live one, or the paused one
        of a paused playbook (a deleted one has none)."""
        return self._live_version(playbook) or self._paused_version(playbook)

    def _pending_draft(self, playbook: dict, live: dict | None) -> dict | None:
        """The latest draft, when it is newer than the live version. An older draft left
        behind (by an earlier publish, or by the one-row-per-save era) is not "the draft"."""
        drafts = (
            self.supabase.table("playbook_versions")
            .select(_VERSION_COLS)
            .eq("playbook_id", playbook["id"])
            .eq("status", "draft")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        if drafts and (live is None or is_newer(drafts[0].get("created_at"), live.get("created_at"))):
            return drafts[0]
        return None

    def _editor_import_draft(self, version_id: str) -> dict | None:
        rows = (
            self.supabase.table("playbook_imports")
            .select("id,draft")
            .eq("id", f"editor:{version_id}")
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def save_structured_draft(
        self,
        company_id: str,
        key: str,
        steps: list,
        entries: list,
        *,
        base_updated_at: str | None = None,
        source_id: str | None = None,
        qualification: list | None = None,
    ) -> dict:
        """The draft holding real steps, objection answers and qualification criteria. A pending draft (newer than
        the live version) is UPDATED in place, so autosave keeps one row; otherwise a new
        draft is inserted. `base_updated_at` is the updated_at the caller last saw: if the
        draft (or, for a first save over a live version, the live one) has moved since,
        StaleDraftError.

        publish_playbook_motion publishes the latest draft and checks the latest import for
        contradictions, so the draft has ONE import row (kind "editor", id
        `editor:{version_id}`, no contradictions), created with it and rewritten by later
        saves. It also carries `draft.source_id`, the material the steps came from.

        `qualification` None leaves the draft's criteria as they are; a new draft starts from
        the live version's (the editor sends what it shows, and a client that does not know
        about criteria must not wipe them)."""
        playbook = self._playbook(company_id, key, create=True)
        if not playbook:
            raise RuntimeError("playbook row missing after upsert")
        if playbook.get("archived_at"):
            playbook = self._unarchive(playbook)
        if source_id is not None and not self.get_source(company_id, source_id):
            source_id = None
        live = self._shown_under_draft(playbook)
        pending = self._pending_draft(playbook, live)
        if pending is not None:
            if base_updated_at and not same_instant(base_updated_at, pending.get("updated_at")):
                raise StaleDraftError()
            patch: dict = {"steps": steps, "entries": entries}
            if qualification is not None:
                patch["qualification"] = qualification
            updated = (
                self.supabase.table("playbook_versions")
                .update(patch)
                .eq("id", pending["id"])
                .eq("status", "draft")  # published in the meantime: not ours to overwrite
                .execute()
            ).data or []
            if not updated:
                raise StaleDraftError()
            version = updated[0]
        else:
            if base_updated_at and not (live and same_instant(base_updated_at, live.get("updated_at"))):
                raise StaleDraftError()
            criteria = qualification if qualification is not None else list((live or {}).get("qualification") or [])
            inserted = (
                self.supabase.table("playbook_versions")
                .insert({
                    "playbook_id": playbook["id"], "status": "draft",
                    "steps": steps, "entries": entries, "qualification": criteria,
                })
                .execute()
            ).data or []
            version = inserted[0] if inserted else {
                "steps": steps, "entries": entries, "qualification": criteria, "status": "draft",
            }
        self._save_editor_import(
            company_id, playbook, live, version, steps, entries, source_id,
            version.get("qualification") or [],
        )
        return version

    def _save_editor_import(
        self, company_id: str, playbook: dict, live: dict | None, version: dict,
        steps: list, entries: list, source_id: str | None, qualification: list | None = None,
    ) -> None:
        from app.services.playbooks.structured import render_text

        if not version.get("id"):
            return
        import_id = f"editor:{version['id']}"
        existing = self._editor_import_draft(version["id"])
        prior = (existing or {}).get("draft") or {}
        effective = source_id or prior.get("source_id")
        if not effective and existing is None and live and live.get("id"):
            # The first edit over a published version keeps pointing at its source.
            effective = ((self._editor_import_draft(live["id"]) or {}).get("draft") or {}).get("source_id")
        draft = {
            "text": render_text(steps, entries, qualification),
            "source_ref": "editor",
            "contradictions": [],
            "version_id": version["id"],
        }
        if effective:
            draft["source_id"] = effective
        if existing is not None:
            self.supabase.table("playbook_imports").update({"draft": draft}).eq("id", import_id).execute()
            return
        self.supabase.table("playbook_imports").insert({
            "id": import_id,
            "company_id": company_id,
            "playbook_id": playbook["id"],
            "kind": "editor",
            "status": "ready",
            "draft": draft,
            "active_version_id": playbook.get("active_version_id"),
        }).execute()

    def editor_snapshot(self, company_id: str, key: str, *, include_draft: bool) -> dict:
        """{state, version, has_live, source, paused}: state is "draft" (the pending draft, only
        for editors), "published" (the active version, or the paused one of a paused playbook)
        or "empty" (also for a deleted type). `source` is the material the shown version was
        structured from, or None."""
        playbook = self._playbook(company_id, key, create=False)
        if not playbook or playbook.get("archived_at"):
            return {"state": "empty", "version": None, "has_live": False, "source": None, "paused": False}
        live = self._shown_under_draft(playbook)
        state, version = "empty", None
        if include_draft:
            pending = self._pending_draft(playbook, live)
            if pending is not None:
                state, version = "draft", pending
        if version is None and live is not None:
            state, version = "published", live
        source = None
        if version is not None and version.get("id"):
            recorded = ((self._editor_import_draft(version["id"]) or {}).get("draft") or {}).get("source_id")
            source = self.get_source(company_id, recorded)
        return {
            "state": state,
            "version": version,
            "has_live": live is not None,
            "source": source,
            "paused": self._is_paused(playbook),
        }

    def editor_version(self, company_id: str, key: str, *, include_draft: bool) -> tuple[str, dict | None]:
        """("draft", v) - the pending draft (only for editors), else ("published", v) - the
        active version, else ("empty", None)."""
        snapshot = self.editor_snapshot(company_id, key, include_draft=include_draft)
        return snapshot["state"], snapshot["version"]

    def discard_draft(self, company_id: str, key: str) -> bool:
        """Deletes the pending draft rows (newer than the live version) and their editor
        import rows. The published version, and every older row, stay."""
        playbook = self._playbook(company_id, key, create=False)
        if not playbook:
            return False
        live = self._shown_under_draft(playbook)
        drafts = (
            self.supabase.table("playbook_versions")
            .select("id,created_at")
            .eq("playbook_id", playbook["id"])
            .eq("status", "draft")
            .execute()
        ).data or []
        ids = [
            row["id"] for row in drafts
            if live is None or is_newer(row.get("created_at"), live.get("created_at"))
        ]
        if not ids:
            return False
        self.supabase.table("playbook_imports").delete().in_("id", [f"editor:{i}" for i in ids]).execute()
        self.supabase.table("playbook_versions").delete().in_("id", ids).eq("status", "draft").execute()
        return True

    def motions(self, company_id: str) -> dict:
        result = self.supabase.rpc("list_playbook_motions", {"p_company": company_id}).execute()
        rows = list(getattr(result, "data", None) or [])
        return {row["sales_motion_key"]: row["motion_status"] for row in rows}

    def publish(self, company_id: str, key: str, role: str) -> dict:
        updated = accept_publish(self.motions(company_id), key, role)
        result = self.supabase.rpc(
            "publish_playbook_motion",
            {"p_company": company_id, "p_motion": key},
        ).execute()
        outcome = getattr(result, "data", None)
        if isinstance(outcome, list):
            outcome = outcome[0] if outcome else None
        if outcome == "contradiction":
            raise PublishError("contradiction")
        if isinstance(outcome, str) and outcome.startswith("published"):
            version = outcome.split(":", 1)[1] if ":" in outcome else ""
            if version:
                self._activated[(company_id, key)] = version
        else:
            raise PublishError("not_a_draft")
        return updated

    def activated(self, company_id: str) -> dict:
        return {
            key: version
            for (company, key), version in self._activated.items()
            if company == company_id
        }

    def add_type(self, company_id: str, key: str, name: str, role: str) -> dict:
        from app.services.playbooks.versions import can_publish

        if not can_publish(role):
            raise PublishError("forbidden")
        cleaned = (key or "").strip()
        if not cleaned:
            raise PublishError("empty_type")
        result = self.supabase.rpc(
            "add_interaction_type",
            {"p_company": company_id, "p_key": cleaned, "p_name": name or cleaned},
        ).execute()
        outcome = getattr(result, "data", None)
        if isinstance(outcome, list):
            outcome = outcome[0] if outcome else None
        if outcome == "empty":
            raise PublishError("empty_type")
        return self.motions(company_id)

    def details(self, company_id: str) -> dict:
        """key -> {"label", "applies_to"} as saved for the company (T7). {} when the
        columns are not there yet (migration 067) or the read fails: types then route by
        their catalog default."""
        try:
            rows = (
                self.supabase.table("playbooks")
                .select("sales_motion_key,label,applies_to,archived_at")
                .eq("company_id", company_id)
                .execute()
            ).data or []
        except Exception:
            return {}
        return {
            row["sales_motion_key"]: {"label": row.get("label"), "applies_to": row.get("applies_to")}
            for row in rows
            if row.get("sales_motion_key") and not row.get("archived_at")
        }

    def version_summaries(self, company_id: str, *, include_draft: bool = True) -> dict:
        """key -> {step_count, answer_count, has_draft} for every type that has a playbook
        row: the version the editor would open (the pending draft for a manager, else the
        live one). Three queries however many types there are (the playbook rows, their
        live versions, their drafts), never one per type. {} when a read fails: the list
        then shows no counts instead of failing."""
        try:
            playbooks = (
                self.supabase.table("playbooks")
                .select("id,sales_motion_key,active_version_id,paused_version_id,archived_at")
                .eq("company_id", company_id)
                .execute()
            ).data or []
            playbooks = [p for p in playbooks if not p.get("archived_at")]
            if not playbooks:
                return {}
            active = [
                p.get("active_version_id") or p.get("paused_version_id")
                for p in playbooks
                if p.get("active_version_id") or p.get("paused_version_id")
            ]
            live_rows = (
                self.supabase.table("playbook_versions").select(_VERSION_COLS).in_("id", active).execute()
            ).data or [] if active else []
            live_by_id = {row["id"]: row for row in live_rows}
            drafts_by_playbook: dict = {}
            draft_rows = (
                self.supabase.table("playbook_versions")
                .select(_VERSION_COLS + ",playbook_id")
                .in_("playbook_id", [p["id"] for p in playbooks])
                .eq("status", "draft")
                .execute()
            ).data or []
        except Exception:
            logger.warning("playbook version summaries unavailable", exc_info=True)
            return {}
        for row in draft_rows:
            best = drafts_by_playbook.get(row["playbook_id"])
            if best is None or is_newer(row.get("created_at"), best.get("created_at")):
                drafts_by_playbook[row["playbook_id"]] = row
        out: dict = {}
        for playbook in playbooks:
            key = playbook.get("sales_motion_key")
            if not key:
                continue
            live = live_by_id.get(playbook.get("active_version_id") or playbook.get("paused_version_id"))
            draft = drafts_by_playbook.get(playbook["id"])
            if draft is not None and live is not None and not is_newer(draft.get("created_at"), live.get("created_at")):
                draft = None  # an older draft left behind is not "the draft"
            pending = include_draft and draft is not None
            out[key] = _summary(draft if pending else live, has_draft=pending, paused=self._is_paused(playbook))
        return out

    # -- pause, resume, delete (docs/superpowers/plans/2026-09-29-playbooks-v2.md, section 16) --

    def pause(self, company_id: str, key: str) -> dict:
        """The active version moves to paused_version_id: everything that reads the active
        version ignores the playbook, the content stays. LifecycleError("not_published") when
        there is no active version."""
        playbook = self._playbook(company_id, key, create=False)
        active = (playbook or {}).get("active_version_id")
        if not playbook or playbook.get("archived_at") or not active:
            raise LifecycleError("not_published")
        moved = (
            self.supabase.table("playbooks")
            .update({"paused_version_id": active, "active_version_id": None})
            .eq("id", playbook["id"])
            .eq("active_version_id", active)  # published or paused by someone else meanwhile: not ours
            .execute()
        ).data or []
        if not moved:
            raise LifecycleError("not_published")
        return self.motions(company_id)

    def resume(self, company_id: str, key: str) -> dict:
        """The paused version is the active one again. LifecycleError("not_paused")."""
        playbook = self._playbook(company_id, key, create=False)
        if not playbook or not self._is_paused(playbook):
            raise LifecycleError("not_paused")
        paused = playbook["paused_version_id"]
        moved = (
            self.supabase.table("playbooks")
            .update({"active_version_id": paused, "paused_version_id": None})
            .eq("id", playbook["id"])
            .eq("paused_version_id", paused)
            .execute()
        ).data or []
        if not moved:
            raise LifecycleError("not_paused")
        return self.motions(company_id)

    def _set_type_active(self, company_id: str, key: str, active: bool) -> None:
        self.supabase.table("interaction_types").update({"active": active}).eq("company_id", company_id).eq(
            "type_key", key
        ).execute()

    def archive(self, company_id: str, key: str) -> dict:
        """"Eliminar", undoable: records the status the type had (archived_state), moves the
        active version to paused_version_id, deletes the playbook's draft versions and their
        editor imports (source documents stay), and deactivates its interaction_types row. A
        type that exists only in interaction_types is deactivated. LifecycleError("not_found")
        when the company has no such type."""
        before = self.motions(company_id).get(key)
        if before is None:
            raise LifecycleError("not_found")
        playbook = self._playbook(company_id, key, create=False)
        if playbook:
            drafts = (
                self.supabase.table("playbook_versions")
                .select("id")
                .eq("playbook_id", playbook["id"])
                .eq("status", "draft")
                .execute()
            ).data or []
            ids = [row["id"] for row in drafts]
            if ids:  # drafts and their import rows first: a half-done delete leaves nothing hidden
                self.supabase.table("playbook_imports").delete().in_("id", [f"editor:{i}" for i in ids]).eq(
                    "kind", "editor"
                ).execute()
                self.supabase.table("playbook_versions").delete().in_("id", ids).eq("status", "draft").execute()
            patch: dict = {"archived_at": _stamp(), "archived_state": before}
            if playbook.get("active_version_id"):
                patch.update(paused_version_id=playbook["active_version_id"], active_version_id=None)
            self.supabase.table("playbooks").update(patch).eq("id", playbook["id"]).execute()
        self._set_type_active(company_id, key, False)
        return self.motions(company_id)

    def restore(self, company_id: str, key: str) -> dict:
        """Undo "Eliminar": back to archived_state (published -> the version is active again;
        paused stays paused; a draft was deleted, so the type is empty) and its interaction type
        active. LifecycleError("not_archived") when it is not deleted."""
        playbook = self._playbook(company_id, key, create=False)
        if playbook:
            if not playbook.get("archived_at"):
                raise LifecycleError("not_archived")
            patch: dict = {"archived_at": None, "archived_state": None}
            paused = playbook.get("paused_version_id")
            if playbook.get("archived_state") == "published" and paused and not playbook.get("active_version_id"):
                patch.update(active_version_id=paused, paused_version_id=None)
            self.supabase.table("playbooks").update(patch).eq("id", playbook["id"]).execute()
        else:
            rows = (
                self.supabase.table("interaction_types")
                .select("type_key,active")
                .eq("company_id", company_id)
                .eq("type_key", key)
                .limit(1)
                .execute()
            ).data or []
            if not rows or rows[0].get("active") is not False:
                raise LifecycleError("not_archived")
        self._set_type_active(company_id, key, True)
        return self.motions(company_id)

    def get_knowledge(self, company_id: str) -> dict | None:
        """{data, source_id, updated_at} of what Vocify knows about the company, None when
        nothing was ever saved."""
        rows = (
            self.supabase.table("company_sales_knowledge")
            .select(_KNOWLEDGE_COLS)
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        ).data or []
        if not rows:
            return None
        row = rows[0]
        return {
            "data": normalize_knowledge(row.get("data")),
            "source_id": row.get("source_id"),
            "updated_at": row.get("updated_at"),
        }

    def save_knowledge(
        self, company_id: str, data: dict, *, base_updated_at: str | None = None, source_id=_UNSET,
    ) -> dict:
        """Replaces the company's knowledge (no draft: it takes effect at once). With
        `base_updated_at`, StaleKnowledgeError when the saved row moved since the caller
        loaded it: the update is filtered on the exact updated_at that was compared, so two
        saves racing on the same base cannot both win."""
        clean = normalize_knowledge(data)
        rows = (
            self.supabase.table("company_sales_knowledge")
            .select(_KNOWLEDGE_COLS)
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        ).data or []
        row = rows[0] if rows else None
        if base_updated_at and not (row and same_instant(base_updated_at, row.get("updated_at"))):
            raise StaleKnowledgeError()
        keep = (row or {}).get("source_id") if source_id is _UNSET else source_id
        if row is None:
            saved = (
                self.supabase.table("company_sales_knowledge")
                .upsert(
                    {"company_id": company_id, "data": clean, "source_id": keep},
                    on_conflict="company_id",
                )
                .execute()
            ).data or []
        else:
            query = (
                self.supabase.table("company_sales_knowledge")
                .update({"data": clean, "source_id": keep})
                .eq("company_id", company_id)
            )
            if base_updated_at:
                query = query.eq("updated_at", row.get("updated_at"))
            saved = query.execute().data or []
            if not saved and base_updated_at:
                raise StaleKnowledgeError()
        result = saved[0] if saved else {}
        return {"data": clean, "source_id": keep, "updated_at": result.get("updated_at")}

    def save_type_meta(self, company_id: str, key: str, *, label=_UNSET, applies_to=_UNSET) -> None:
        """Saves a type's label and/or routing rule on its playbooks row, creating the row
        (listed as "missing" by list_playbook_motions) when the type has none yet."""
        playbook = self._playbook(company_id, key, create=True)
        if not playbook:
            raise RuntimeError("playbook row missing after upsert")
        patch: dict = {}
        if label is not _UNSET:
            patch["label"] = label
        if applies_to is not _UNSET:
            patch["applies_to"] = applies_to
        if patch:
            self.supabase.table("playbooks").update(patch).eq("id", playbook["id"]).execute()
