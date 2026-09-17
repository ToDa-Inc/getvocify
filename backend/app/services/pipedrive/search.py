"""Pipedrive item search wrappers (v2). Term min 2 chars unless exact_match."""

from __future__ import annotations

from typing import Any, Optional

from .client import PipedriveClient, unwrap_data, unwrap_search_items


def _term_or_empty(term: Optional[str], *, exact_match: bool = False) -> str:
    t = (term or "").strip()
    if not t:
        return ""
    if exact_match:
        return t
    return t if len(t) >= 2 else ""


def primary_email(person: dict[str, Any]) -> str:
    emails = person.get("emails") or []
    for e in emails:
        if isinstance(e, dict) and e.get("primary") and e.get("value"):
            return str(e["value"])
    for e in emails:
        if isinstance(e, dict) and e.get("value"):
            return str(e["value"])
    if isinstance(person.get("email"), list) and person["email"]:
        first = person["email"][0]
        if isinstance(first, dict):
            return str(first.get("value") or "")
        return str(first)
    return str(person.get("email") or "")


def primary_phone(person: dict[str, Any]) -> Optional[str]:
    phones = person.get("phones") or person.get("phone") or []
    if isinstance(phones, str):
        return phones or None
    for p in phones:
        if isinstance(p, dict) and p.get("primary") and p.get("value"):
            return str(p["value"])
    for p in phones:
        if isinstance(p, dict) and p.get("value"):
            return str(p["value"])
        if isinstance(p, str) and p:
            return p
    return None


class PipedriveSearchService:
    def __init__(self, client: PipedriveClient) -> None:
        self.client = client

    async def _search(self, path: str, term: str, *, fields: Optional[str] = None, limit: int = 10) -> list[dict[str, Any]]:
        q = _term_or_empty(term)
        if not q:
            return []
        params: dict[str, Any] = {"term": q, "limit": min(limit, 100)}
        if fields:
            params["fields"] = fields
        return unwrap_search_items(await self.client.get(path, params=params))

    async def search_deals(self, term: str, *, limit: int = 10) -> list[dict[str, Any]]:
        return await self._search("/deals/search", term, fields="title", limit=limit)

    async def search_persons(self, term: str, *, fields: str = "name,email,phone", limit: int = 10) -> list[dict[str, Any]]:
        return await self._search("/persons/search", term, fields=fields, limit=limit)

    async def search_organizations(self, term: str, *, limit: int = 10) -> list[dict[str, Any]]:
        return await self._search("/organizations/search", term, fields="name", limit=limit)

    async def get_deal(self, deal_id: str) -> dict[str, Any]:
        data = unwrap_data(await self.client.get(f"/deals/{deal_id}"))
        return data if isinstance(data, dict) else {}

    async def get_person(self, person_id: str) -> dict[str, Any]:
        data = unwrap_data(await self.client.get(f"/persons/{person_id}"))
        return data if isinstance(data, dict) else {}

    async def get_organization(self, org_id: str) -> dict[str, Any]:
        data = unwrap_data(await self.client.get(f"/organizations/{org_id}"))
        return data if isinstance(data, dict) else {}

    async def deals_for_person(self, person_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        raw = unwrap_data(await self.client.get("/deals", params={"person_id": person_id, "limit": limit}))
        return raw if isinstance(raw, list) else []
