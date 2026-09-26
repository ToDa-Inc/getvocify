"""Ask reads on Pipedrive. What the provider cannot read comes back unavailable, never empty."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.services.crm_providers.coverage import read_envelope
from app.services.pipedrive.page_context import assoc_id, deal_raw_extraction, person_names
from app.services.pipedrive.record_urls import build_pipedrive_record_url, company_domain_from_api_domain
from app.services.pipedrive.search import primary_email, primary_phone

NOT_AVAILABLE = "not_available_for_pipedrive"
UNREAD_CONTEXT = ("notes", "tasks", "calls", "emails")
READ_TOOLS = frozenset({
    "search_contacts",
    "get_contact",
    "inspect_record",
    "search_companies",
    "get_company",
    "search_deals",
    "get_deal",
    "list_associated_deals",
})
_PERSON_FIELDS = ("label", "owner_id", "add_time", "update_time", "last_activity_date", "next_activity_date")
_DEAL_FIELDS = ("status", "currency", "expected_close_date", "owner_id", "pipeline_id", "add_time", "update_time")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first_text(values: Any) -> Optional[str]:
    for value in values or []:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _status(exc: BaseException) -> Optional[int]:
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    return status


class PipedriveReader:
    provider = "pipedrive"

    def __init__(self, search: Any, connection: dict) -> None:
        self.search = search
        meta = connection.get("metadata") or {}
        self.domain = meta.get("company_domain") or company_domain_from_api_domain(meta.get("api_domain"))
        self.connection_id = str(connection.get("id") or "pipedrive")

    @classmethod
    def from_provider(cls, provider: Any) -> "PipedriveReader":
        return cls(provider._search(), provider._connection)

    def _url(self, object_type: str, record_id: Optional[str]) -> Optional[str]:
        if not self.domain or not record_id:
            return None
        return build_pipedrive_record_url(self.domain, object_type, record_id)

    def _envelope(self, *, coverage: str, reason: str, object_type: str, tool: str) -> dict:
        envelope = read_envelope(
            items=[],
            coverage=coverage,
            observed_at=_now(),
            connection_id=self.connection_id,
            object_type=object_type,
            reason=reason,
        )
        return {"ok": False, **envelope, "provider": self.provider, "tool": tool}

    def unavailable(self, tool: str, ctx: Any = None) -> dict:
        _mark(ctx, "partial")
        return self._envelope(coverage="unavailable", reason=NOT_AVAILABLE, object_type="record", tool=tool)

    def _failure(self, tool: str, exc: BaseException, ctx: Any) -> dict:
        if _status(exc) in {401, 403}:
            _mark(ctx, "forbidden")
            return self._envelope(coverage="forbidden", reason="pipedrive_forbidden", object_type="record", tool=tool)
        _mark(ctx, "unavailable")
        return self._envelope(coverage="unavailable", reason="provider_unavailable", object_type="record", tool=tool)

    def contact_brief(self, person: dict) -> dict:
        pid = assoc_id(person.get("id")) or ""
        _first, _last, name = person_names(person)
        url = self._url("person", pid)
        org = person.get("organization") if isinstance(person.get("organization"), dict) else None
        brief = {
            "object": "contact",
            "id": pid,
            "name": name or pid,
            "email": primary_email(person) or _first_text(person.get("emails")),
            "phone": primary_phone(person),
            "jobtitle": person.get("job_title"),
            "company_name": (org or {}).get("name") or person.get("org_name"),
            "url": url,
            "contact_id": pid,
            "contact_url": url,
        }
        return {key: value for key, value in brief.items() if value is not None}

    def company_brief(self, org: dict) -> dict:
        cid = assoc_id(org.get("id")) or ""
        brief = {
            "object": "company",
            "id": cid,
            "name": org.get("name"),
            "address": org.get("address") if isinstance(org.get("address"), str) else None,
            "url": self._url("organization", cid),
            "company_id": cid,
        }
        return {key: value for key, value in brief.items() if value is not None}

    def deal_brief(self, deal: dict) -> dict:
        did = assoc_id(deal.get("id")) or ""
        shaped = deal_raw_extraction(deal)
        url = self._url("deal", did)
        brief = {
            "object": "deal",
            "id": did,
            "name": shaped.get("dealname"),
            "amount": shaped.get("amount"),
            "currency": deal.get("currency"),
            "stage": shaped.get("dealstage"),
            "status": deal.get("status"),
            "url": url,
            "deal_id": did,
            "deal_url": url,
        }
        return {key: value for key, value in brief.items() if value is not None}

    async def _deals_for(self, person_id: str) -> list[dict]:
        return [self.deal_brief(row) for row in await self.search.deals_for_person(person_id, limit=8)]

    async def hydrate_contact(self, person_id: str, ctx: Any) -> dict:
        person = await self.search.get_person(person_id)
        brief = self.contact_brief(person)
        brief["fields"] = {key: person[key] for key in _PERSON_FIELDS if person.get(key)}
        org_id = assoc_id(person.get("org_id"))
        if org_id:
            try:
                brief["company"] = self.company_brief(await self.search.get_organization(org_id))
            except Exception:
                brief["company"] = {"id": org_id, "company_id": org_id}
        try:
            brief["deals"] = await self._deals_for(person_id)
        except Exception:
            brief["deals_coverage"] = "unavailable"
        brief["coverage"] = "partial"
        brief["reason"] = NOT_AVAILABLE
        brief["unavailable"] = list(UNREAD_CONTEXT)
        _mark(ctx, "partial")
        return brief

    async def run(self, name: str, args: dict, ctx: Any) -> dict:
        if name not in READ_TOOLS:
            return self.unavailable(name, ctx)
        try:
            return await self._read(name, args, ctx)
        except Exception as exc:
            return self._failure(name, exc, ctx)

    async def _read(self, name: str, args: dict, ctx: Any) -> dict:
        if name == "search_contacts":
            hits = await self.search.search_persons(str(args.get("query") or ""), limit=8)
            if len(hits) == 1:
                contacts = [await self.hydrate_contact(assoc_id(hits[0].get("id")) or "", ctx)]
            else:
                contacts = [self.contact_brief(hit) for hit in hits]
            return {"contacts": contacts, "provider": self.provider}
        if name == "get_contact":
            return await self.hydrate_contact(str(args["contact_id"]), ctx)
        if name == "inspect_record":
            copilot = (getattr(ctx, "artifacts", None) or {}).get("copilot") or {}
            contact_id = args.get("contact_id") or copilot.get("last_contact_id")
            deal_id = args.get("deal_id") or copilot.get("last_deal_id")
            if contact_id:
                return await self.hydrate_contact(str(contact_id), ctx)
            if deal_id:
                deal = await self.search.get_deal(str(deal_id))
                brief = self.deal_brief(deal)
                brief["fields"] = {key: deal[key] for key in _DEAL_FIELDS if deal.get(key)}
                brief["coverage"] = "partial"
                brief["reason"] = NOT_AVAILABLE
                brief["unavailable"] = ["notes", "tasks"]
                _mark(ctx, "partial")
                return brief
            return {"ok": False, "error": "no contact or deal in focus"}
        if name == "search_companies":
            hits = await self.search.search_organizations(str(args.get("query") or ""), limit=8)
            return {"companies": [self.company_brief(hit) for hit in hits], "provider": self.provider}
        if name == "get_company":
            return self.company_brief(await self.search.get_organization(str(args["company_id"])))
        if name == "search_deals":
            hits = await self.search.search_deals(str(args.get("query") or ""), limit=8)
            return {"deals": [self.deal_brief(hit) for hit in hits], "provider": self.provider}
        if name == "get_deal":
            return self.deal_brief(await self.search.get_deal(str(args["deal_id"])))
        if name == "list_associated_deals":
            return {"deals": await self._deals_for(str(args["contact_id"])), "provider": self.provider}
        return self.unavailable(name, ctx)


def _mark(ctx: Any, coverage: str) -> None:
    artifacts = getattr(ctx, "artifacts", None)
    if not isinstance(artifacts, dict):
        return
    current = artifacts.get("crm_coverage")
    rank = {"partial": 1, "unavailable": 2, "forbidden": 3}
    if rank.get(coverage, 0) > rank.get(current, 0):
        artifacts["crm_coverage"] = coverage
