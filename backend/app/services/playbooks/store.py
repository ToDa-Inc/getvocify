"""Playbook state. Memory is the test default. Postgres is what startup installs."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.services.playbooks.versions import (
    PublishError,
    StaleDraftError,
    accept_publish,
    is_newer,
    parse_ts,
    same_instant,
)

SOURCE_PREFIX = "source:"
_VERSION_COLS = "id,status,steps,entries,created_at,updated_at"


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

    def get_import(self, company_id: str, import_id: str):
        record = self._imports.get(import_id)
        if not record or record.get("company_id") != company_id:
            return None
        return record

    def save_import(self, company_id: str, record: dict, sales_motion_key: str | None) -> None:
        self._imports[record["import_id"]] = {**record, "company_id": company_id}
        if sales_motion_key and record.get("status") == "ready" and not record.get("published"):
            company = self._motions.setdefault(company_id, {})
            if company.get(sales_motion_key) != "published":
                company[sales_motion_key] = "draft"
        if sales_motion_key and record.get("status") == "ready":
            self._latest[(company_id, sales_motion_key)] = record

    def save_source(self, company_id: str, key: str, kind: str, name: str | None, text: str) -> dict:
        """Keeps the original material a playbook was structured from. Creates no version."""
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
        return dict(self._motions.get(company_id) or {})

    def save_structured_draft(
        self,
        company_id: str,
        key: str,
        steps: list,
        entries: list,
        *,
        base_updated_at: str | None = None,
        source_id: str | None = None,
    ) -> dict:
        """Test double of SupabasePlaybookStore.save_structured_draft: a pending draft is
        updated in place (same id), otherwise a new one is created."""
        slot = (company_id, key)
        pending = self._structured.get(slot)
        live = self._published_versions.get(slot)
        if source_id is not None and not self.get_source(company_id, source_id):
            source_id = None
        if pending is not None:
            if base_updated_at and not same_instant(base_updated_at, pending.get("updated_at")):
                raise StaleDraftError()
            pending["steps"] = steps
            pending["entries"] = entries
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
                "created_at": stamp,
                "updated_at": stamp,
                "source_id": source_id if source_id is not None else (live or {}).get("source_id"),
            }
            self._structured[slot] = version
        company = self._motions.setdefault(company_id, {})
        if company.get(key) != "published":
            company[key] = "draft"
        self._latest[slot] = {"draft": {"contradictions": []}}
        return dict(version)

    def editor_snapshot(self, company_id: str, key: str, *, include_draft: bool) -> dict:
        """{state, version, has_live, source}: state is "draft" (the pending draft, only for
        editors), "published" (the live version) or "empty"."""
        draft = self._structured.get((company_id, key))
        live = self._published_versions.get((company_id, key))
        if include_draft and draft and draft.get("status") == "draft":
            state, version = "draft", draft
        elif live:
            state, version = "published", live
        else:
            state, version = "empty", None
        return {
            "state": state,
            "version": dict(version) if version else None,
            "has_live": live is not None,
            "source": self.get_source(company_id, (version or {}).get("source_id")),
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
        if company.get(key) != "published":
            company[key] = "missing"
        return True

    def publish(self, company_id: str, key: str, role: str) -> dict:
        latest = self._latest.get((company_id, key)) or {}
        if (latest.get("draft") or {}).get("contradictions"):
            raise PublishError("contradiction")
        updated = accept_publish(self.motions(company_id), key, role)
        self._motions.setdefault(company_id, {})[key] = "published"
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
        company = self._motions.setdefault(company_id, {})
        company.setdefault(cleaned, "missing")
        del name
        return dict(company)

    def details(self, company_id: str) -> dict:
        """key -> {"label", "applies_to"} as saved for the company (T7)."""
        return {
            key: dict(meta)
            for (company, key), meta in self._details.items()
            if company == company_id
        }

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
            .select("id,active_version_id")
            .eq("company_id", company_id)
            .eq("sales_motion_key", key)
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def save_source(self, company_id: str, key: str, kind: str, name: str | None, text: str) -> dict:
        """Keeps the original material a playbook was structured from (playbook_imports,
        id `source:{uuid}`). Creates no version."""
        playbook = self._playbook(company_id, key, create=True)
        if not playbook:
            raise RuntimeError("playbook row missing after upsert")
        source_id = f"{SOURCE_PREFIX}{uuid.uuid4()}"
        self.supabase.table("playbook_imports").insert({
            "id": source_id,
            "company_id": company_id,
            "playbook_id": playbook["id"],
            "kind": kind,
            "status": "ready",
            "draft": {"text": text, "name": name or "", "source_ref": f"{kind}:{source_id}"},
            "active_version_id": playbook.get("active_version_id"),
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

    def _live_version(self, playbook: dict) -> dict | None:
        active = playbook.get("active_version_id")
        if not active:
            return None
        rows = (
            self.supabase.table("playbook_versions")
            .select(_VERSION_COLS)
            .eq("id", active)
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

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
    ) -> dict:
        """The draft holding real steps and objection answers. A pending draft (newer than
        the live version) is UPDATED in place, so autosave keeps one row; otherwise a new
        draft is inserted. `base_updated_at` is the updated_at the caller last saw: if the
        draft (or, for a first save over a live version, the live one) has moved since,
        StaleDraftError.

        publish_playbook_motion publishes the latest draft and checks the latest import for
        contradictions, so the draft has ONE import row (kind "editor", id
        `editor:{version_id}`, no contradictions), created with it and rewritten by later
        saves. It also carries `draft.source_id`, the material the steps came from."""
        playbook = self._playbook(company_id, key, create=True)
        if not playbook:
            raise RuntimeError("playbook row missing after upsert")
        if source_id is not None and not self.get_source(company_id, source_id):
            source_id = None
        live = self._live_version(playbook)
        pending = self._pending_draft(playbook, live)
        if pending is not None:
            if base_updated_at and not same_instant(base_updated_at, pending.get("updated_at")):
                raise StaleDraftError()
            updated = (
                self.supabase.table("playbook_versions")
                .update({"steps": steps, "entries": entries})
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
            inserted = (
                self.supabase.table("playbook_versions")
                .insert({"playbook_id": playbook["id"], "status": "draft", "steps": steps, "entries": entries})
                .execute()
            ).data or []
            version = inserted[0] if inserted else {"steps": steps, "entries": entries, "status": "draft"}
        self._save_editor_import(company_id, playbook, live, version, steps, entries, source_id)
        return version

    def _save_editor_import(
        self, company_id: str, playbook: dict, live: dict | None, version: dict,
        steps: list, entries: list, source_id: str | None,
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
            "text": render_text(steps, entries),
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
        """{state, version, has_live, source}: state is "draft" (the pending draft, only for
        editors), "published" (the active version) or "empty". `source` is the material
        the shown version was structured from, or None."""
        playbook = self._playbook(company_id, key, create=False)
        if not playbook:
            return {"state": "empty", "version": None, "has_live": False, "source": None}
        live = self._live_version(playbook)
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
        return {"state": state, "version": version, "has_live": live is not None, "source": source}

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
        live = self._live_version(playbook)
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
                .select("sales_motion_key,label,applies_to")
                .eq("company_id", company_id)
                .execute()
            ).data or []
        except Exception:
            return {}
        return {
            row["sales_motion_key"]: {"label": row.get("label"), "applies_to": row.get("applies_to")}
            for row in rows
            if row.get("sales_motion_key")
        }

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
