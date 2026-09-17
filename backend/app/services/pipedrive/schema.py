"""Deal/person/org fields, pipelines, stages. Cache as deals|contacts|companies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.models.memo import MemoExtraction

from .client import PipedriveClient, unwrap_data

OBJECT_PATHS = {
    "deals": "/dealFields",
    "contacts": "/personFields",
    "companies": "/organizationFields",
}

CORE_DEAL_FIELDS = frozenset(
    {
        "title",
        "value",
        "currency",
        "expected_close_date",
        "stage_id",
        "pipeline_id",
        "status",
        "org_id",
        "person_id",
        "owner_id",
        "lost_reason",
        "probability",
        "visible_to",
        "label_ids",
    }
)


class PipedriveSchemaService:
    CACHE_TTL_SECONDS = 3600

    def __init__(
        self,
        client: PipedriveClient,
        supabase: Any = None,
        connection_id: Optional[str] = None,
    ) -> None:
        self.client = client
        self.supabase = supabase
        self.connection_id = connection_id
        self._memory: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}

    async def list_fields(self, object_type: str) -> list[dict[str, Any]]:
        if object_type not in OBJECT_PATHS:
            raise ValueError(f"Unsupported object_type: {object_type}")
        now = datetime.now(timezone.utc)
        cached = self._memory.get(object_type)
        if cached and (now - cached[0]).total_seconds() < self.CACHE_TTL_SECONDS:
            return cached[1]
        if self.supabase and self.connection_id:
            db = await self._from_db_cache(object_type)
            if db is not None:
                self._memory[object_type] = (now, db)
                return db
        raw = unwrap_data(await self.client.get(OBJECT_PATHS[object_type]))
        fields = raw if isinstance(raw, list) else []
        self._memory[object_type] = (now, fields)
        if self.supabase and self.connection_id:
            await self._save_db_cache(object_type, fields)
        return fields

    async def list_pipelines(self) -> list[dict[str, Any]]:
        raw = unwrap_data(await self.client.get("/pipelines"))
        return raw if isinstance(raw, list) else []

    async def list_stages(self, pipeline_id: Optional[str] = None) -> list[dict[str, Any]]:
        params = {}
        if pipeline_id:
            params["pipeline_id"] = pipeline_id
        raw = unwrap_data(await self.client.get("/stages", params=params or None))
        return raw if isinstance(raw, list) else []

    async def get_curated_field_specs(self, field_names: list[str], object_type: str = "deals") -> list[dict[str, Any]]:
        fields = await self.list_fields(object_type)
        by_key = {str(f.get("key")): f for f in fields if f.get("key")}
        out: list[dict[str, Any]] = []
        for name in field_names:
            f = by_key.get(name)
            if not f:
                out.append({"name": name, "label": name, "type": "string"})
                continue
            spec: dict[str, Any] = {
                "name": name,
                "label": f.get("name") or name,
                "type": f.get("field_type") or "string",
                "description": "",
            }
            opts = f.get("options") or []
            if opts:
                spec["options"] = [
                    {"value": str(o.get("id") if o.get("id") is not None else o.get("label") or ""), "label": o.get("label") or str(o.get("id") or "")}
                    for o in opts
                    if isinstance(o, dict)
                ]
            out.append(spec)
        return out

    async def resolve_stage_id(
        self,
        stage_value: Optional[str],
        default_stage_id: Optional[str],
        pipeline_id: Optional[str],
    ) -> Optional[str]:
        if default_stage_id and not stage_value:
            return str(default_stage_id)
        if not stage_value or not str(stage_value).strip():
            return str(default_stage_id) if default_stage_id else None
        val = str(stage_value).strip()
        stages = await self.list_stages(pipeline_id)
        vlower = val.lower()
        for s in stages:
            sid = s.get("id")
            label = str(s.get("name") or "")
            if sid is not None and str(sid) == val:
                return str(sid)
            if label.lower() == vlower:
                return str(sid) if sid is not None else None
        return str(default_stage_id) if default_stage_id else None

    def map_extraction_to_deal_fields(
        self,
        extraction: MemoExtraction,
        *,
        title: Optional[str] = None,
        stage_id: Optional[str] = None,
        pipeline_id: Optional[str] = None,
        org_id: Optional[str] = None,
        person_id: Optional[str] = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if title:
            fields["title"] = title
        if extraction.dealAmount is not None:
            fields["value"] = extraction.dealAmount
        if extraction.dealCurrency:
            fields["currency"] = extraction.dealCurrency
        if extraction.closeDate:
            fields["expected_close_date"] = extraction.closeDate
        if stage_id:
            fields["stage_id"] = int(stage_id)
        if pipeline_id:
            fields["pipeline_id"] = int(pipeline_id)
        if org_id:
            fields["org_id"] = int(org_id)
        if person_id:
            fields["person_id"] = int(person_id)
        return fields

    def split_write_payload(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Core keys stay top-level; other keys go in v2 `custom_fields`."""
        core: dict[str, Any] = {}
        custom: dict[str, Any] = {}
        for k, v in fields.items():
            if k in CORE_DEAL_FIELDS:
                core[k] = v
            else:
                custom[k] = v
        if custom:
            core["custom_fields"] = custom
        return core

    async def _from_db_cache(self, object_type: str) -> Optional[list[dict[str, Any]]]:
        try:
            r = (
                self.supabase.table("crm_schemas")
                .select("*")
                .eq("connection_id", self.connection_id)
                .eq("object_type", object_type)
                .maybe_single()
                .execute()
            )
            if not r or not r.data:
                return None
            row = r.data
            fetched = row.get("fetched_at")
            if not fetched:
                return None
            ft = datetime.fromisoformat(str(fetched).replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - ft).total_seconds() > 86400:
                return None
            props = row.get("properties")
            if isinstance(props, list):
                return props
            if isinstance(props, dict) and isinstance(props.get("fields"), list):
                return props["fields"]
            return None
        except Exception:
            return None

    async def _save_db_cache(self, object_type: str, fields: list[dict[str, Any]]) -> None:
        try:
            self.supabase.table("crm_schemas").upsert(
                {
                    "connection_id": self.connection_id,
                    "object_type": object_type,
                    "properties": fields,
                    "pipelines": None,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="connection_id,object_type",
            ).execute()
        except Exception:
            pass
