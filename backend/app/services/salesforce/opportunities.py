"""Salesforce Opportunity: map MemoExtraction, create, update, get."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from app.models.memo import MemoExtraction

from .client import SalesforceClient
from .schema import SalesforceSchemaService

logger = logging.getLogger(__name__)


def _normalize_close_date_for_salesforce(raw: Optional[str]) -> Optional[str]:
    """
    Salesforce CloseDate must be YYYY-MM-DD (date only). User/LLM often sends DD/MM/YYYY.
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Already ISO date
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            datetime.strptime(s[:10], "%Y-%m-%d")
            return s[:10]
        except ValueError:
            pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(s[:10], fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.warning("Could not parse closeDate for Salesforce CloseDate: %r", raw)
    return None


# Do not send these via generic map/update
SF_SKIP_RAW = frozenset({
    "Name", "Amount", "CloseDate", "StageName", "Description",
    "summary", "painPoints", "nextSteps", "objections", "decisionMakers", "confidence",
    "contactName", "companyName", "contactEmail", "contactPhone", "contactRole",
    "dealname", "dealstage", "closedate", "amount",
})


class SalesforceOpportunityService:
    def __init__(self, client: SalesforceClient, schema: SalesforceSchemaService) -> None:
        self.client = client
        self.schema = schema

    def _generate_name(self, extraction: MemoExtraction, contact_name: Optional[str] = None) -> str:
        if extraction.companyName:
            n = extraction.companyName.strip()
            return n if n.lower().endswith("deal") else f"{n} Deal"
        if contact_name:
            n = contact_name.strip()
            return f"{n} Deal" if n else "New Deal"
        if extraction.contactName:
            return f"{extraction.contactName.strip()} Deal"
        return "New Deal"

    def map_extraction_to_fields(
        self,
        extraction: MemoExtraction,
        *,
        deal_name: Optional[str] = None,
        stage_name: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        fields["Name"] = (deal_name or self._generate_name(extraction))[:120]
        if extraction.dealAmount is not None:
            fields["Amount"] = float(extraction.dealAmount)
        cd_iso = _normalize_close_date_for_salesforce(extraction.closeDate)
        if cd_iso:
            fields["CloseDate"] = cd_iso
        if stage_name:
            fields["StageName"] = stage_name
        if extraction.summary:
            fields["Description"] = extraction.summary

        if extraction.raw_extraction:
            for key, value in extraction.raw_extraction.items():
                if key in SF_SKIP_RAW or value is None:
                    continue
                if isinstance(value, (dict, list)) and key not in ("competitors",):
                    continue
                fields[key] = value

        if account_id:
            fields["AccountId"] = account_id
        return fields

    async def get(self, opportunity_id: str, field_names: Optional[list[str]] = None) -> dict[str, Any]:
        if field_names:
            fields_param = ",".join(field_names)
            return await self.client.get(f"/sobjects/Opportunity/{opportunity_id}", params={"fields": fields_param})
        return await self.client.get(f"/sobjects/Opportunity/{opportunity_id}")

    async def create(self, fields: dict[str, Any]) -> str:
        resp = await self.client.post("/sobjects/Opportunity/", json_body=fields)
        oid = (resp or {}).get("id")
        if not oid:
            raise ValueError("Salesforce did not return opportunity id")
        return oid

    async def update(self, opportunity_id: str, fields: dict[str, Any]) -> None:
        await self.client.patch(f"/sobjects/Opportunity/{opportunity_id}", json_body=fields)
