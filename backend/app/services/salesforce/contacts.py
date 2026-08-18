"""Salesforce Contact CRUD."""

from __future__ import annotations

from typing import Any, Optional

from app.models.memo import MemoExtraction
from app.services.extraction import _clean_extracted_name

from .client import SalesforceClient
from .search import SalesforceSearchService


def _split_name(full: Optional[str]) -> tuple[str, str]:
    if not full or not str(full).strip():
        return "", ""
    parts = str(full).strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


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
        from app.services.hubspot.contact_identity import real_contact_email_or_none

        email = real_contact_email_or_none(extraction.contactEmail)
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
        from app.services.hubspot.contact_identity import real_contact_email_or_none

        email = real_contact_email_or_none(
            extraction.contactEmail or raw.get("contactEmail") or raw.get("contact_email")
        ) or ""
        name = extraction.contactName or _clean_extracted_name(raw.get("contactName")) or _clean_extracted_name(raw.get("contact_name"))
        phone = (extraction.contactPhone or raw.get("contactPhone") or "").strip()
        if not email and not (name and str(name).strip()) and not phone:
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
