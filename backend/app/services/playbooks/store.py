"""Playbook state. Memory is the test default. Postgres is what startup installs."""

from __future__ import annotations

import uuid

from app.services.playbooks.versions import PublishError, accept_publish


class MemoryPlaybookStore:
    def __init__(
        self,
        motions: dict,
        imports: dict,
        latest: dict | None = None,
        activated: dict | None = None,
        structured: dict | None = None,
        published_versions: dict | None = None,
    ):
        self._motions = motions
        self._imports = imports
        self._latest = latest if latest is not None else {}
        self._activated = activated if activated is not None else {}
        # The API builds a new instance per request: shared dicts keep editor drafts alive.
        self._structured = structured if structured is not None else {}
        self._published_versions = published_versions if published_versions is not None else {}

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

    def motions(self, company_id: str) -> dict:
        return dict(self._motions.get(company_id) or {})

    def save_structured_draft(self, company_id: str, key: str, steps: list, entries: list) -> dict:
        """Test double of SupabasePlaybookStore.save_structured_draft."""
        version = {"id": str(uuid.uuid4()), "status": "draft", "steps": steps, "entries": entries}
        self._structured[(company_id, key)] = version
        company = self._motions.setdefault(company_id, {})
        if company.get(key) != "published":
            company[key] = "draft"
        self._latest[(company_id, key)] = {"draft": {"contradictions": []}}
        return version

    def editor_version(self, company_id: str, key: str, *, include_draft: bool) -> tuple[str, dict | None]:
        draft = self._structured.get((company_id, key))
        if include_draft and draft and draft.get("status") == "draft":
            return "draft", draft
        live = self._published_versions.get((company_id, key))
        return ("published", live) if live else ("empty", None)

    def publish(self, company_id: str, key: str, role: str) -> dict:
        latest = self._latest.get((company_id, key)) or {}
        if (latest.get("draft") or {}).get("contradictions"):
            raise PublishError("contradiction")
        updated = accept_publish(self.motions(company_id), key, role)
        self._motions.setdefault(company_id, {})[key] = "published"
        draft = self._structured.pop((company_id, key), None)
        version_id = (draft or {}).get("id") or str(uuid.uuid4())
        if draft:
            self._published_versions[(company_id, key)] = {**draft, "status": "published"}
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

    def save_structured_draft(self, company_id: str, key: str, steps: list, entries: list) -> dict:
        """A new draft version holding real steps and objection answers. publish_playbook_motion
        publishes the latest draft, and checks the latest import for contradictions, so an
        import row (no contradictions, kind "editor") is written alongside it."""
        from app.services.playbooks.structured import render_text

        playbook = self._playbook(company_id, key, create=True)
        if not playbook:
            raise RuntimeError("playbook row missing after upsert")
        inserted = (
            self.supabase.table("playbook_versions")
            .insert({"playbook_id": playbook["id"], "status": "draft", "steps": steps, "entries": entries})
            .execute()
        ).data or []
        version = inserted[0] if inserted else {"steps": steps, "entries": entries, "status": "draft"}
        self.supabase.table("playbook_imports").insert({
            "id": f"editor:{uuid.uuid4()}",
            "company_id": company_id,
            "playbook_id": playbook["id"],
            "kind": "editor",
            "status": "ready",
            "draft": {"text": render_text(steps, entries), "source_ref": "editor", "contradictions": []},
            "active_version_id": playbook.get("active_version_id"),
        }).execute()
        return version

    def editor_version(self, company_id: str, key: str, *, include_draft: bool) -> tuple[str, dict | None]:
        """("draft", v) - the latest unpublished draft (only for editors), else
        ("published", v) - the active version, else ("empty", None)."""
        playbook = self._playbook(company_id, key, create=False)
        if not playbook:
            return "empty", None
        live = None
        active = playbook.get("active_version_id")
        if active:
            rows = (
                self.supabase.table("playbook_versions")
                .select("id,status,steps,entries,created_at")
                .eq("id", active)
                .limit(1)
                .execute()
            ).data or []
            live = rows[0] if rows else None
        if include_draft:
            drafts = (
                self.supabase.table("playbook_versions")
                .select("id,status,steps,entries,created_at")
                .eq("playbook_id", playbook["id"])
                .eq("status", "draft")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            ).data or []
            # An older draft left behind by an earlier publish is not "the draft": only one
            # newer than the live version is.
            if drafts and (live is None or str(drafts[0].get("created_at") or "") > str(live.get("created_at") or "")):
                return "draft", drafts[0]
        return ("published", live) if live else ("empty", None)

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
