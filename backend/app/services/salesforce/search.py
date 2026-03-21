"""SOQL search helpers."""

from __future__ import annotations

import re
from typing import Any, Optional

from .client import SalesforceClient
from .exceptions import SalesforceError


def _soql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


class SalesforceSearchService:
    def __init__(self, client: SalesforceClient) -> None:
        self.client = client

    async def query(self, soql: str) -> list[dict[str, Any]]:
        try:
            resp = await self.client.get("/query", params={"q": soql})
            return (resp or {}).get("records") or []
        except SalesforceError:
            return []

    async def find_account_by_name(self, name: Optional[str]) -> Optional[dict[str, Any]]:
        if not name or not name.strip():
            return None
        term = name.strip()[:80]
        soql = (
            "SELECT Id, Name FROM Account WHERE Name LIKE "
            + _soql_string(f"%{term}%")
            + " LIMIT 1"
        )
        rows = await self.query(soql)
        return rows[0] if rows else None

    async def find_contact_by_email(self, email: Optional[str]) -> Optional[dict[str, Any]]:
        if not email or not email.strip():
            return None
        em = email.strip().lower()
        soql = "SELECT Id, FirstName, LastName, Email, AccountId FROM Contact WHERE Email = " + _soql_string(em) + " LIMIT 1"
        rows = await self.query(soql)
        return rows[0] if rows else None

    async def find_opportunities_by_term(
        self,
        term: str,
        *,
        limit: int = 10,
        stage_filter: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        if not term or not term.strip():
            return []
        safe = re.sub(r"['\\%]", " ", term.strip())[:120]
        like = _soql_string(f"%{safe}%")
        where = f"Name LIKE {like}"
        if stage_filter:
            where += f" AND StageName = {_soql_string(stage_filter)}"
        soql = (
            f"SELECT Id, Name, Amount, StageName, CloseDate, LastModifiedDate, AccountId "
            f"FROM Opportunity WHERE {where} ORDER BY LastModifiedDate DESC LIMIT {min(limit, 50)}"
        )
        return await self.query(soql)
