"""
Approval preview service for showing proposed CRM updates.

Uses the same property mapping as sync (map_extraction_to_properties) so that
proposed_updates reflects exactly what the config's allowed_deal_fields specify,
and what the LLM extracted from the transcript.
"""

from uuid import UUID
from typing import Optional, Any
from app.models.memo import MemoExtraction
from app.models.approval import ApprovalPreview, ProposedUpdate, DealMatch, AvailableField
from .client import HubSpotClient
from .exceptions import HubSpotError
from .deals import HubSpotDealService
from .schema import HubSpotSchemaService
from .associations import HubSpotAssociationService
from .contacts import HubSpotContactService
from .companies import HubSpotCompanyService


def _format_value_for_display(value: Any) -> str:
    """Format a value for display in ProposedUpdate.new_value/current_value"""
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


class HubSpotPreviewService:
    """
    Builds approval previews showing what will be updated in HubSpot.
    
    Uses map_extraction_to_properties (same as sync) so proposed_updates
    reflects config's allowed_deal_fields and LLM extraction.
    """

    def __init__(
        self,
        client: HubSpotClient,
        deal_service: HubSpotDealService,
        schema_service: HubSpotSchemaService,
        associations: Optional[HubSpotAssociationService] = None,
        contact_service: Optional[HubSpotContactService] = None,
        company_service: Optional[HubSpotCompanyService] = None,
    ):
        self.client = client
        self.deals = deal_service
        self.schema = schema_service
        self.associations = associations
        self.contact_service = contact_service
        self.company_service = company_service

    async def build_preview(
        self,
        memo_id: UUID,
        transcript: str,
        extraction: MemoExtraction,
        matched_deals: list[DealMatch],
        selected_deal_id: Optional[str] = None,
        allowed_fields: Optional[list[str]] = None,
    ) -> ApprovalPreview:
        """
        Build approval preview with proposed updates.
        
        Uses config's allowed_deal_fields and the same mapping as sync.
        Shows what the LLM extracted for each allowed field.
        """
        transcript_summary = transcript[:200] + "..." if len(transcript) > 200 else transcript
        transcript_full = transcript if transcript else None

        if allowed_fields is None:
            allowed_fields = ["dealname", "amount", "description", "closedate"]

        is_new_deal = selected_deal_id is None
        selected_deal: Optional[DealMatch] = None
        proposed_updates: list[ProposedUpdate] = []

        # Get properties using same logic as sync (uses extraction + raw_extraction)
        properties = self.deals.map_extraction_to_properties(extraction)

        # Filter by allowed_fields - only show what config permits
        filtered_properties = {k: v for k, v in properties.items() if k in allowed_fields}

        # Get field labels and metadata from schema (fallback to field name if schema fetch fails)
        field_labels: dict[str, str] = {}
        field_specs_map: dict[str, dict] = {}
        try:
            props_keys = list(filtered_properties.keys())
            field_specs = await self.schema.get_curated_field_specs("deals", props_keys)
            for s in field_specs:
                field_labels[s["name"]] = s["label"]
                field_specs_map[s["name"]] = s
        except Exception:
            pass

        # Contact and Company - always show when extracted (not in allowed_fields, but critical for user)
        contact_name = extraction.contactName
        if not contact_name and extraction.companyName:
            contact_name = f"Contact at {extraction.companyName}"  # fallback when only company
        if contact_name:
            proposed_updates.append(ProposedUpdate(
                field_name="contact_name",
                field_label="Contact Name",
                current_value=None,
                new_value=contact_name,
                extraction_confidence=extraction.confidence.get("fields", {}).get("contactName", 0.8),
            ))
        if extraction.companyName:
            proposed_updates.append(ProposedUpdate(
                field_name="company_name",
                field_label="Company",
                current_value=None,
                new_value=extraction.companyName,
                extraction_confidence=extraction.confidence.get("fields", {}).get("companyName", 0.8),
            ))

        # Next steps (create HubSpot tasks) - always show in preview so user can confirm
        next_steps = extraction.nextSteps or []
        if not next_steps and extraction.raw_extraction and extraction.raw_extraction.get("hs_next_step"):
            hs_next = extraction.raw_extraction["hs_next_step"]
            next_steps = [hs_next] if isinstance(hs_next, str) else (hs_next if isinstance(hs_next, list) else [])
        for i, step in enumerate(next_steps):
            if step and str(step).strip():
                proposed_updates.append(ProposedUpdate(
                    field_name=f"next_step_task_{i}",
                    field_label="Next Step (Task)" if i == 0 else f"Next Step {i + 1} (Task)",
                    current_value=None,
                    new_value=str(step).strip(),
                    extraction_confidence=extraction.confidence.get("fields", {}).get("next_step", 0.8),
                ))

        # For display: use human-readable extraction values when available
        def _display_value(field_name: str, value: Any) -> str:
            if value is None or value == "":
                return ""
            if field_name == "closedate" and extraction.closeDate:
                return extraction.closeDate  # ISO date more readable than timestamp
            return _format_value_for_display(value)

        if is_new_deal:
            # New deal: all values are "new", no current values
            for field_name, new_value in filtered_properties.items():
                if new_value is None or new_value == "":
                    continue
                spec = field_specs_map.get(field_name, {})
                label = field_labels.get(field_name, field_name.replace("_", " ").title())
                confidence = extraction.confidence.get("fields", {}).get(field_name, 0.7)
                proposed_updates.append(ProposedUpdate(
                    field_name=field_name,
                    field_label=label,
                    current_value=None,
                    new_value=_display_value(field_name, new_value),
                    extraction_confidence=confidence,
                    field_type=spec.get("type"),
                    options=spec.get("options"),
                ))
        else:
            # Update existing deal: compare with current values
            selected_deal = next(
                (d for d in matched_deals if d.deal_id == selected_deal_id),
                None
            )

            if not selected_deal:
                try:
                    deal = await self.deals.get(selected_deal_id)
                    company_name = None
                    contact_name = None
                    if self.associations and self.company_service:
                        try:
                            cids = await self.associations.get_associations("deals", selected_deal_id, "companies")
                            if cids:
                                comp = await self.company_service.get(cids[0])
                                company_name = comp.properties.get("name")
                        except Exception:
                            pass
                    contact_email = None
                    if self.associations and self.contact_service:
                        try:
                            ctids = await self.associations.get_associations("deals", selected_deal_id, "contacts")
                            if ctids:
                                contact = await self.contact_service.get(ctids[0])
                                cp = contact.properties
                                contact_name = f"{cp.get('firstname', '')} {cp.get('lastname', '')}".strip() or None
                                contact_email = cp.get("email")
                        except Exception:
                            pass
                    selected_deal = DealMatch(
                        deal_id=deal.id,
                        deal_name=deal.properties.get("dealname", "Unknown Deal"),
                        company_name=company_name,
                        contact_name=contact_name,
                        contact_email=contact_email,
                        match_reason="Manual Selection",
                        match_confidence=1.0,
                        stage=deal.properties.get("dealstage"),
                        amount=deal.properties.get("amount"),
                        last_updated=deal.properties.get("hs_lastmodifieddate", ""),
                    )
                except Exception:
                    pass

            if selected_deal:
                try:
                    current_deal = await self.deals.get(selected_deal_id)
                    current_props = current_deal.properties

                    for field_name, new_value in filtered_properties.items():
                        if new_value is None or new_value == "":
                            continue

                        current_value = current_props.get(field_name)

                        # For description, append mode (same as sync)
                        if field_name == "description" and current_value:
                            new_display = f"{current_value}\n\n{_format_value_for_display(new_value)}"
                        else:
                            new_display = _display_value(field_name, new_value)

                        current_display = _display_value(field_name, current_value)

                        # Only show if there's a change
                        if current_display != new_display:
                            spec = field_specs_map.get(field_name, {})
                            label = field_labels.get(field_name, field_name.replace("_", " ").title())
                            confidence = extraction.confidence.get("fields", {}).get(field_name, 0.7)
                            proposed_updates.append(ProposedUpdate(
                                field_name=field_name,
                                field_label=label,
                                current_value=current_display or "(empty)",
                                new_value=new_display,
                                extraction_confidence=confidence,
                                field_type=spec.get("type"),
                                options=spec.get("options"),
                            ))
                except Exception:
                    pass

        # Compute available_fields: allowed_deal_fields not yet in proposed_updates
        proposed_field_names = {
            u.field_name for u in proposed_updates
            if u.field_name in allowed_fields
            and not u.field_name.startswith("next_step_task_")
        }
        available_field_names = [f for f in allowed_fields if f not in proposed_field_names]
        available_fields_list: list[AvailableField] = []
        if available_field_names:
            try:
                avail_specs = await self.schema.get_curated_field_specs("deals", available_field_names)
                for s in avail_specs:
                    available_fields_list.append(AvailableField(
                        name=s["name"],
                        label=s["label"],
                        type=s.get("type", "string"),
                        options=s.get("options"),
                    ))
            except Exception:
                for name in available_field_names:
                    available_fields_list.append(AvailableField(
                        name=name,
                        label=name.replace("_", " ").title(),
                        type="string",
                    ))

        # Only include contact when we have email - HubSpot requires it; we don't invent placeholders
        new_contact = None
        if extraction.contactEmail and str(extraction.contactEmail).strip():
            new_contact = {
                "name": contact_name,
                "email": extraction.contactEmail.strip(),
                "phone": extraction.contactPhone,
            }
        new_company = {"name": extraction.companyName} if extraction.companyName else None

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
