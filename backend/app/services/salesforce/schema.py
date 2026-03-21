"""
Describe Opportunity (and related) for field metadata and StageName picklist.
Caches in crm_schemas when supabase + connection_id are set.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from supabase import Client

from app.models.memo import MemoExtraction

from .client import SalesforceClient


class SalesforceSchemaService:
    CACHE_TTL_SECONDS = 3600

    def __init__(
        self,
        client: SalesforceClient,
        supabase: Optional[Client] = None,
        connection_id: Optional[str] = None,
    ) -> None:
        self.client = client
        self.supabase = supabase
        self.connection_id = connection_id
        self._memory_describe: Optional[dict[str, Any]] = None
        self._memory_at: Optional[datetime] = None

    async def describe_opportunity(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        if (
            self._memory_describe
            and self._memory_at
            and (now - self._memory_at).total_seconds() < self.CACHE_TTL_SECONDS
        ):
            return self._memory_describe

        if self.supabase and self.connection_id:
            cached = await self._from_db_cache("Opportunity")
            if cached:
                self._memory_describe = cached
                self._memory_at = now
                return cached

        d = await self.client.get("/sobjects/Opportunity/describe")
        self._memory_describe = d
        self._memory_at = now
        if self.supabase and self.connection_id and isinstance(d, dict):
            await self._save_db_cache("Opportunity", d)
        return d

    async def _from_db_cache(self, object_type: str) -> Optional[dict[str, Any]]:
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
            if isinstance(props, dict) and props.get("fields"):
                return props
            return None
        except Exception:
            return None

    async def _save_db_cache(self, object_type: str, describe: dict[str, Any]) -> None:
        try:
            self.supabase.table("crm_schemas").upsert(
                {
                    "connection_id": self.connection_id,
                    "object_type": object_type,
                    "properties": describe,
                    "pipelines": None,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="connection_id,object_type",
            ).execute()
        except Exception:
            pass

    async def get_stage_picklist_values(self) -> list[dict[str, str]]:
        d = await self.describe_opportunity()
        fields = d.get("fields") or []
        for f in fields:
            if f.get("name") == "StageName" and f.get("picklistValues"):
                return [{"label": x.get("label", ""), "value": x.get("value", "")} for x in f["picklistValues"]]
        return []

    async def get_curated_field_specs(
        self,
        field_names: list[str],
    ) -> list[dict[str, Any]]:
        d = await self.describe_opportunity()
        by_name = {f.get("name"): f for f in (d.get("fields") or [])}
        out: list[dict[str, Any]] = []
        for name in field_names:
            f = by_name.get(name)
            if not f:
                continue
            spec: dict[str, Any] = {
                "name": name,
                "label": f.get("label") or name,
                "type": f.get("type") or "string",
                "description": (f.get("inlineHelpText") or "") or "",
            }
            pvs = f.get("picklistValues") or []
            if pvs:
                spec["options"] = [{"value": x.get("value"), "label": x.get("label")} for x in pvs]
            out.append(spec)
        return out

    async def resolve_stage_name(self, stage_value: Optional[str], default_stage: Optional[str]) -> Optional[str]:
        """Map label or API value to valid StageName picklist value."""
        if default_stage and not stage_value:
            stage_value = default_stage
        if not stage_value or not str(stage_value).strip():
            return None
        val = str(stage_value).strip()
        picklist = await self.get_stage_picklist_values()
        if not picklist:
            return val
        vlower = val.lower()
        for p in picklist:
            if (p.get("value") or "").lower() == vlower:
                return p["value"]
            if (p.get("label") or "").lower() == vlower:
                return p["value"]
        return None
