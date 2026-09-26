"""Approval preview for Salesforce (same ApprovalPreview shape as HubSpot)."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.models.approval import ApprovalPreview, AvailableField, DealMatch, ProposedUpdate
from app.models.memo import MemoExtraction

from .opportunities import SalesforceOpportunityService
from .schema import SalesforceSchemaService
from .search import SalesforceSearchService

from .client import SalesforceClient


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if isinstance(v, (int, float)):
        return str(v)
    return str(v)


class SalesforcePreviewService:
    def __init__(
        self,
        client: SalesforceClient,
        opportunities: SalesforceOpportunityService,
        schema: SalesforceSchemaService,
        search: SalesforceSearchService,
    ) -> None:
        self.client = client
        self.opportunities = opportunities
        self.schema = schema
        self.search = search

    async def build_preview(
        self,
        memo_id: UUID,
        transcript: str,
        extraction: MemoExtraction,
        matched_deals: list[DealMatch],
        selected_deal_id: Optional[str],
        allowed_fields: Optional[list[str]],
        default_stage_name: Optional[str] = None,
    ) -> ApprovalPreview:
        if allowed_fields is None:
            allowed_fields = ["Name", "Amount", "CloseDate", "StageName", "Description"]

        transcript_summary = transcript[:200] + "..." if len(transcript) > 200 else transcript
        transcript_full = transcript or None
        is_new_deal = not selected_deal_id
        selected_deal: Optional[DealMatch] = None
        proposed_updates: list[ProposedUpdate] = []

        resolved_stage = await self.schema.resolve_stage_name(extraction.dealStage, default_stage_name)
        props = self.opportunities.map_extraction_to_fields(extraction, stage_name=resolved_stage)
        filtered = {k: v for k, v in props.items() if k in allowed_fields}

        field_specs = await self.schema.get_curated_field_specs(allowed_fields)
        field_labels = {s["name"]: s["label"] for s in field_specs}
        field_specs_map = {s["name"]: s for s in field_specs}

        if is_new_deal:
            for field_name, new_value in filtered.items():
                if new_value is None or new_value == "":
                    continue
                spec = field_specs_map.get(field_name, {})
                proposed_updates.append(
                    ProposedUpdate(
                        field_name=field_name,
                        field_label=field_labels.get(field_name, field_name),
                        current_value=None,
                        new_value=_fmt(new_value),
                        extraction_confidence=extraction.confidence.get("fields", {}).get(field_name, 0.7),
                        field_type=spec.get("type"),
                        options=spec.get("options"),
                    )
                )
        else:
            selected_deal = next((d for d in matched_deals if d.deal_id == selected_deal_id), None)
            current: dict[str, Any] = {}
            if not selected_deal:
                try:
                    current = await self.opportunities.get(
                        selected_deal_id,
                        field_names=allowed_fields,
                    )
                    acc_name = None
                    aid = current.get("AccountId")
                    if aid:
                        try:
                            acc = await self.client.get(f"/sobjects/Account/{aid}", params={"fields": "Name"})
                            acc_name = acc.get("Name")
                        except Exception:
                            pass
                    selected_deal = DealMatch(
                        deal_id=selected_deal_id,
                        deal_name=current.get("Name") or "Opportunity",
                        company_name=acc_name,
                        match_reason="Manual Selection",
                        match_confidence=1.0,
                        stage=current.get("StageName"),
                        amount=str(current.get("Amount")) if current.get("Amount") is not None else None,
                        last_updated=str(current.get("LastModifiedDate") or ""),
                    )
                except Exception:
                    pass
            elif selected_deal_id:
                try:
                    current = await self.opportunities.get(
                        selected_deal_id,
                        field_names=allowed_fields,
                    )
                except Exception:
                    current = {}

            if selected_deal and current:
                for field_name, new_value in filtered.items():
                    if new_value is None or new_value == "":
                        continue
                    if field_name == "Name":
                        continue
                    cur = current.get(field_name)
                    new_disp = _fmt(new_value)
                    if field_name == "Description" and cur:
                        new_disp = f"{_fmt(cur)}\n\n---\n\n{new_disp}"
                    cur_disp = _fmt(cur)
                    if cur_disp != new_disp:
                        spec = field_specs_map.get(field_name, {})
                        proposed_updates.append(
                            ProposedUpdate(
                                field_name=field_name,
                                field_label=field_labels.get(field_name, field_name),
                                current_value=cur_disp or "(empty)",
                                new_value=new_disp,
                                extraction_confidence=extraction.confidence.get("fields", {}).get(field_name, 0.7),
                                field_type=spec.get("type"),
                                options=spec.get("options"),
                            )
                        )

        if is_new_deal:
            cn = extraction.contactName or (
                f"Contact at {extraction.companyName}" if extraction.companyName else None
            )
            if cn:
                proposed_updates.insert(
                    0,
                    ProposedUpdate(
                        field_name="contact_name",
                        field_label="Contact Name",
                        current_value=None,
                        new_value=cn,
                        extraction_confidence=extraction.confidence.get("fields", {}).get("contactName", 0.8),
                    ),
                )
            if extraction.companyName:
                proposed_updates.insert(
                    0,
                    ProposedUpdate(
                        field_name="company_name",
                        field_label="Company",
                        current_value=None,
                        new_value=extraction.companyName,
                        extraction_confidence=extraction.confidence.get("fields", {}).get("companyName", 0.8),
                    ),
                )

        proposed_field_names = {
            u.field_name
            for u in proposed_updates
            if u.field_name in allowed_fields and not u.field_name.startswith("next_step_task_")
        }
        available_fields_list: list[AvailableField] = []
        for name in allowed_fields:
            if name not in proposed_field_names:
                spec = field_specs_map.get(name, {})
                available_fields_list.append(
                    AvailableField(
                        name=name,
                        label=spec.get("label", name),
                        type=spec.get("type", "string"),
                        options=spec.get("options"),
                    )
                )

        new_contact = None
        new_company = None
        if is_new_deal:
            from app.services.hubspot.contact_identity import real_contact_email_or_none

            email = real_contact_email_or_none(extraction.contactEmail)
            name = (extraction.contactName or "").strip() or None
            phone = (extraction.contactPhone or "").strip() or None
            if name or email or phone:
                new_contact = {
                    "name": name,
                    "email": email,
                    "phone": phone,
                }
            if extraction.companyName:
                new_company = {"name": extraction.companyName}

        return ApprovalPreview(
            memo_id=memo_id,
            transcript_summary=transcript_summary,
            transcript=transcript_full,
            matched_deals=matched_deals,
            selected_deal=selected_deal,
            is_new_deal=is_new_deal,
            proposed_updates=proposed_updates,
            available_fields=available_fields_list,
            new_contact=new_contact,
            new_company=new_company,
        )
