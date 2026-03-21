"""Salesforce Contact CRUD."""

from __future__ import annotations

import re
from typing import Any, Optional

from app.models.memo import MemoExtraction

from .client import SalesforceClient
from .search import SalesforceSearchService


def _split_name(full: Optional[str]) -> tuple[str, str]:
    if not full or not str(full).strip():
        return "", ""
    parts = str(full).strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _placeholder_email(contact_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", contact_name.strip().lower())
    slug = slug.strip("-") or "contact"
    return f"{slug}@lead.getvocify.com"


class SalesforceContactService:
    def __init__(self, client: SalesforceClient, search: SalesforceSearchService) -> None:
        self.client = client
        self.search = search

    def map_extraction_to_fields(
        self,
        extraction: MemoExtraction,
        account_id: Optional[str] = None,
    ) -> dict[str, Any]:
        fn, ln = _split_name(extraction.contactName)
        if not fn and not ln and extraction.companyName:
            fn = "Contact"
            ln = f"at {extraction.companyName}"[:80]
        email = (extraction.contactEmail or "").strip() or None
        if not email and (fn or ln):
            email = _placeholder_email(f"{fn} {ln}".strip() or "contact")
        body: dict[str, Any] = {}
        if fn:
            body["FirstName"] = fn[:40]
        if ln:
            body["LastName"] = ln[:80]
        elif fn:
            body["LastName"] = "."
        if email:
            body["Email"] = email[:80]
        if extraction.contactPhone:
            body["Phone"] = str(extraction.contactPhone)[:40]
        if account_id:
            body["AccountId"] = account_id
        return body

    async def find_or_create(
        self,
        extraction: MemoExtraction,
        account_id: Optional[str],
    ) -> Optional[str]:
        raw = extraction.raw_extraction or {}
        email = (extraction.contactEmail or raw.get("contactEmail") or raw.get("contact_email") or "").strip()
        name = extraction.contactName or raw.get("contactName") or raw.get("contact_name")
        if not email and not (name and str(name).strip()):
            return None
        if email:
            row = await self.search.find_contact_by_email(email)
            if row:
                cid = row.get("Id")
                fields = self.map_extraction_to_fields(extraction, account_id)
                fields.pop("Email", None)
                if len(fields) > 1 or "AccountId" in fields:
                    try:
                        await self.client.patch(f"/sobjects/Contact/{cid}", json_body=fields)
                    except Exception:
                        pass
                return cid
        body = self.map_extraction_to_fields(extraction, account_id)
        if not body.get("LastName"):
            body["LastName"] = "Unknown"
        resp = await self.client.post("/sobjects/Contact/", json_body=body)
        return (resp or {}).get("id")
