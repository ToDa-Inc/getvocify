"""Match MemoExtraction to Salesforce Opportunities (DealMatch shape for shared UI)."""

from __future__ import annotations

import logging
from typing import Optional

from app.models.approval import DealMatch
from app.models.memo import MemoExtraction

from .client import SalesforceClient
from .search import SalesforceSearchService

logger = logging.getLogger(__name__)


class SalesforceMatchingService:
    def __init__(self, client: SalesforceClient, search: SalesforceSearchService) -> None:
        self.search = search
        self.client = client

    async def find_matching_deals(
        self,
        extraction: MemoExtraction,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        """
        pipeline_id unused for Salesforce (stages are a flat picklist); kept for protocol symmetry.
        """
        matches: list[DealMatch] = []
        seen: set[str] = set()

        async def add_rows(rows: list[dict], reason: str, base_conf: float) -> None:
            for i, row in enumerate(rows):
                oid = row.get("Id")
                if not oid or oid in seen:
                    continue
                seen.add(oid)
                conf = max(0.5, base_conf - i * 0.1)
                matches.append(
                    DealMatch(
                        deal_id=oid,
                        deal_name=row.get("Name") or "Opportunity",
                        company_name=None,
                        contact_name=None,
                        contact_email=None,
                        amount=str(row.get("Amount")) if row.get("Amount") is not None else None,
                        stage=row.get("StageName"),
                        last_updated=str(row.get("LastModifiedDate") or ""),
                        match_confidence=min(1.0, conf),
                        match_reason=reason,
                    )
                )
                if len(matches) >= limit:
                    return

        if extraction.companyName:
            acc = await self.search.find_account_by_name(extraction.companyName.strip())
            if acc and acc.get("Id"):
                aid = str(acc["Id"])
                if not aid.replace("-", "").isalnum() or len(aid.replace("-", "")) < 15:
                    aid = ""
                if aid:
                    soql = (
                        f"SELECT Id, Name, Amount, StageName, LastModifiedDate FROM Opportunity "
                        f"WHERE AccountId = '{aid}' ORDER BY LastModifiedDate DESC LIMIT {limit}"
                    )
                    rows = await self.search.query(soql)
                    await add_rows(rows, "Account match", 0.95)

        if len(matches) < limit and extraction.companyName:
            rows = await self.search.find_opportunities_by_term(
                extraction.companyName.strip(), limit=limit
            )
            await add_rows(rows, "Name contains company", 0.75)

        if len(matches) < limit and extraction.contactEmail:
            rows = await self.search.find_opportunities_by_term(
                extraction.contactEmail.strip(), limit=limit
            )
            await add_rows(rows, "Search", 0.55)

        return matches[:limit]
