"""Playbook state. Memory is the test default. Postgres is what startup installs."""

from __future__ import annotations

from app.services.playbooks.versions import PublishError, accept_publish


class MemoryPlaybookStore:
    def __init__(self, motions: dict, imports: dict):
        self._motions = motions
        self._imports = imports

    def get_import(self, import_id: str):
        return self._imports.get(import_id)

    def save_import(self, company_id: str, record: dict, sales_motion_key: str | None) -> None:
        self._imports[record["import_id"]] = record
        if sales_motion_key and record.get("status") == "ready" and not record.get("published"):
            company = self._motions.setdefault(company_id, {})
            if company.get(sales_motion_key) != "published":
                company[sales_motion_key] = "draft"

    def motions(self, company_id: str) -> dict:
        return dict(self._motions.get(company_id) or {})

    def publish(self, company_id: str, key: str, role: str) -> dict:
        updated = accept_publish(self.motions(company_id), key, role)
        self._motions.setdefault(company_id, {})[key] = "published"
        return updated

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

    def get_import(self, import_id: str):
        result = (
            self.supabase.table("playbook_imports")
            .select("id,status,draft,active_version_id")
            .eq("id", import_id)
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
            },
        ).execute()

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
        if outcome != "published":
            raise PublishError("not_a_draft")
        return updated

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
