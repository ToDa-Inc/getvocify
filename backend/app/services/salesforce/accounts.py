"""Salesforce Account CRUD."""

from __future__ import annotations

from typing import Any, Optional

from app.models.memo import MemoExtraction

from .client import SalesforceClient
from .search import SalesforceSearchService


class SalesforceAccountService:
    def __init__(self, client: SalesforceClient, search: SalesforceSearchService) -> None:
        self.client = client
        self.search = search

    async def find_or_create(self, extraction: MemoExtraction) -> Optional[str]:
        name = (extraction.companyName or "").strip()
        if not name:
            return None
        existing = await self.search.find_account_by_name(name)
        if existing:
            return existing.get("Id")
        body = {"Name": name[:255]}
        resp = await self.client.post("/sobjects/Account/", json_body=body)
        return (resp or {}).get("id")
