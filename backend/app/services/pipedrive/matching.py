"""Match MemoExtraction to Pipedrive deals."""

from __future__ import annotations

import logging
from typing import Optional

from app.models.approval import DealMatch
from app.models.memo import MemoExtraction

from .search import PipedriveSearchService, primary_email

logger = logging.getLogger(__name__)


class PipedriveMatchingService:
    def __init__(self, search: PipedriveSearchService) -> None:
        self.search = search

    async def find_matching_deals(
        self,
        extraction: MemoExtraction,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        del pipeline_id
        matches: list[DealMatch] = []
        seen: set[str] = set()

        def add(row: dict, reason: str, conf: float) -> None:
            did = row.get("id")
            if did is None:
                return
            sid = str(did)
            if sid in seen:
                return
            seen.add(sid)
            matches.append(
                DealMatch(
                    deal_id=sid,
                    deal_name=row.get("title") or "Deal",
                    company_name=row.get("org_name") or (
                        (row.get("org_id") or {}).get("name") if isinstance(row.get("org_id"), dict) else None
                    ),
                    contact_name=row.get("person_name"),
                    contact_email=primary_email(row) or None,
                    amount=str(row["value"]) if row.get("value") is not None else None,
                    stage=str(row.get("stage_id")) if row.get("stage_id") is not None else None,
                    last_updated=str(row.get("update_time") or row.get("updated_at") or ""),
                    match_confidence=min(1.0, conf),
                    match_reason=reason,
                )
            )

        if extraction.companyName:
            try:
                for i, row in enumerate(await self.search.search_deals(extraction.companyName.strip(), limit=limit)):
                    add(row, "Name contains company", max(0.5, 0.85 - i * 0.1))
            except Exception as e:
                logger.warning("Pipedrive deal search by company failed: %s", e)

        if len(matches) < limit and extraction.contactName:
            try:
                for i, row in enumerate(await self.search.search_deals(extraction.contactName.strip(), limit=limit)):
                    add(row, "Name contains contact", max(0.5, 0.7 - i * 0.1))
            except Exception as e:
                logger.warning("Pipedrive deal search by contact failed: %s", e)

        if len(matches) < limit and extraction.contactEmail:
            try:
                for i, row in enumerate(await self.search.search_deals(extraction.contactEmail.strip(), limit=limit)):
                    add(row, "Search", max(0.5, 0.55 - i * 0.05))
            except Exception as e:
                logger.warning("Pipedrive deal search by email failed: %s", e)

        return matches[:limit]
