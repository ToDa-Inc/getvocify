"""
Approval preview service for showing proposed CRM updates.

Uses the same property mapping as sync so proposed_updates reflects
allowed_*_fields (deals, contacts, companies, line_items) and LLM extraction.
"""

from uuid import UUID
from typing import Optional, Any
from app.models.memo import MemoExtraction
from app.models.approval import ApprovalPreview, ProposedUpdate, DealMatch, AvailableField, ContactMatch
from .client import HubSpotClient
from app.services.deal_merge import merge_description
from .deals import HubSpotDealService, _sanitize_enum_properties
from .tasks import format_next_step_task, _next_step_schedule_hints
from .schema import HubSpotSchemaService
from .associations import HubSpotAssociationService
from .contacts import HubSpotContactService
from .companies import HubSpotCompanyService
from .object_properties import (
    contact_properties_from_extraction,
    company_properties_from_extraction,
    line_items_from_extraction,
)
from app.services.extraction_policy import drop_call_unsafe_props, is_identity_name_field


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
        default_pipeline_id: Optional[str] = None,
        default_stage_id: Optional[str] = None,
        allowed_contact_fields: Optional[list[str]] = None,
        allowed_company_fields: Optional[list[str]] = None,
        allowed_line_item_fields: Optional[list[str]] = None,
        selected_contact: Optional[ContactMatch] = None,
        contact_candidates: Optional[list[ContactMatch]] = None,
        create_new_deal: bool = False,
    ) -> ApprovalPreview:
        """
        Build a preview from the same allowlist, stage-resolution, and validation
        paths used by sync so every proposed update is actually deliverable.

        Modes:
        - selected_deal_id set → update that deal (+ optional contact anchor)
        - create_new_deal → create deal preview
        - selected_contact only → contact/company fields, skip deal (Option A)
        - none of the above → legacy create-new-deal preview
        """
        transcript_summary = transcript[:200] + "..." if len(transcript) > 200 else transcript
        transcript_full = transcript if transcript else None

        if allowed_fields is None:
            allowed_fields = ["dealname", "amount", "description", "closedate"]
        if allowed_contact_fields is None:
            allowed_contact_fields = ["firstname", "lastname", "email", "phone", "jobtitle"]
        if allowed_company_fields is None:
            allowed_company_fields = ["name", "domain"]
        if allowed_line_item_fields is None:
            allowed_line_item_fields = ["name", "quantity", "price"]

        if selected_deal_id:
            is_new_deal = False
            skip_deal = False
        elif create_new_deal:
            is_new_deal = True
            skip_deal = False
            selected_deal_id = None
        elif selected_contact is not None:
            is_new_deal = False
            skip_deal = True
            selected_deal_id = None
        else:
            is_new_deal = True
            skip_deal = False

        selected_deal: Optional[DealMatch] = None
        proposed_updates: list[ProposedUpdate] = []

        # For a brand new deal, the AI-inferred stage is always shown/applied since
        # there's nothing to override. For an existing deal, stage is only touched
        # when the user explicitly enabled "dealstage" in Editable Fields - same rule
        # as every other field, so a rep's manual pipeline management is never
        # silently overridden by the preview/sync.
        show_stage = (is_new_deal and not skip_deal) or "dealstage" in allowed_fields
        if "dealstage" in allowed_fields or not show_stage:
            preview_fields = allowed_fields
        else:
            preview_fields = [*allowed_fields, "dealstage"]

        # For an existing deal, scope stage resolution to its own current pipeline -
        # otherwise an inferred stage label could resolve against a different
        # pipeline's stage of the same name, which sync would then reject (or worse,
        # preview one thing and sync would resolve a different one).
        existing_deal_pipeline_id: Optional[str] = None
        if selected_deal_id and not is_new_deal:
            try:
                _pipeline_probe = await self.deals.get(selected_deal_id, properties=["pipeline"])
                existing_deal_pipeline_id = (_pipeline_probe.properties or {}).get("pipeline")
            except Exception:
                pass

        filtered_properties: dict[str, Any] = {}
        if not skip_deal:
            # Get properties using the exact same mapping + validation as sync, so a
            # field only shows up here if it will actually be written on approval.
            properties = await self.deals.map_extraction_to_properties_with_stage(
                extraction,
                allowed_fields=allowed_fields,
                default_pipeline_id=default_pipeline_id if is_new_deal else existing_deal_pipeline_id,
                default_stage_id=default_stage_id if is_new_deal else None,
                is_new_deal=is_new_deal,
            )
            properties = await _sanitize_enum_properties(self.schema, properties)
            filtered_properties = {k: v for k, v in properties.items() if k in preview_fields}

        field_labels: dict[str, str] = {}
        field_specs_map: dict[str, dict] = {}
        try:
            multi_specs = await self.schema.get_multi_object_field_specs(
                allowed_deal_fields=preview_fields,
                allowed_contact_fields=allowed_contact_fields,
                allowed_company_fields=allowed_company_fields,
                allowed_line_item_fields=allowed_line_item_fields,
            )
            for s in multi_specs:
                object_type = s.get("object_type") or "deals"
                key = f"{object_type}:{s['name']}"
                field_labels[key] = s["label"]
                field_specs_map[key] = s
                if object_type == "deals":
                    field_labels[s["name"]] = s["label"]
                    field_specs_map[s["name"]] = s

            # Deal stage options must come from the target pipeline's own stages,
            # rather than the flattened property options across all pipelines.
            stage_pipeline_id = default_pipeline_id if is_new_deal else existing_deal_pipeline_id
            deal_schema = await self.schema.get_deal_schema()
            stage_pipeline = next(
                (p for p in deal_schema.pipelines if p.id == stage_pipeline_id),
                deal_schema.pipelines[0] if deal_schema.pipelines else None,
            )
            if stage_pipeline:
                field_specs_map["dealstage"] = {
                    "name": "dealstage",
                    "label": field_labels.get("dealstage", "Deal Stage"),
                    "type": "enumeration",
                    "options": [{"value": s.id, "label": s.label} for s in stage_pipeline.stages],
                }
                field_labels["dealstage"] = field_specs_map["dealstage"]["label"]
        except Exception:
            pass

        # Next steps (HubSpot tasks) require a deal — skip in contact-only mode
        if not skip_deal:
            next_steps = extraction.nextSteps or []
            if not next_steps and extraction.raw_extraction and extraction.raw_extraction.get("hs_next_step"):
                hs_next = extraction.raw_extraction["hs_next_step"]
                next_steps = [hs_next] if isinstance(hs_next, str) else (hs_next if isinstance(hs_next, list) else [])
            for i, step in enumerate(next_steps):
                if step and str(step).strip():
                    schedule_hints = _next_step_schedule_hints(extraction)
                    hint = schedule_hints[i] if i < len(schedule_hints) else None
                    formatted = format_next_step_task(
                        str(step).strip(),
                        contact_name=extraction.contactName,
                        schedule_hint=hint or None,
                    )
                    proposed_updates.append(ProposedUpdate(
                        field_name=f"next_step_task_{i}",
                        field_label="Next Step (Task)" if i == 0 else f"Next Step {i + 1} (Task)",
                        current_value=None,
                        new_value=formatted.subject,
                        extraction_confidence=extraction.confidence.get("fields", {}).get("next_step", 0.8),
                        object_type="task",
                    ))

        # For display: use human-readable extraction values when available.
        # Note: enum/select fields intentionally keep their raw API value here (not
        # the label) - the frontend maps value -> label for display using the
        # `options` list on each ProposedUpdate, while the underlying value stays the
        # one that actually gets sent to HubSpot (and drives the edit dropdown).
        def _display_value(field_name: str, value: Any) -> str:
            if value is None or value == "":
                return ""
            if field_name == "closedate" and extraction.closeDate:
                return extraction.closeDate
            return _format_value_for_display(value)

        current_contact_props: dict = {}
        current_company_props: dict = {}
        current_contact_name_from_deal: Optional[str] = None
        current_company_name_from_deal: Optional[str] = None

        # Contact-first: load current props from the resolved contact (not only via deal)
        if selected_contact and self.contact_service:
            try:
                contact = await self.contact_service.get(
                    selected_contact.contact_id,
                    properties=list(
                        set(
                            allowed_contact_fields
                            + ["email", "firstname", "lastname", "phone", "jobtitle"]
                        )
                    ),
                )
                current_contact_props = contact.properties or {}
                cp = current_contact_props
                current_contact_name_from_deal = (
                    f"{cp.get('firstname', '')} {cp.get('lastname', '')}".strip() or None
                )
            except Exception:
                pass
            if selected_contact.company_id and self.company_service:
                try:
                    comp = await self.company_service.get(
                        selected_contact.company_id,
                        properties=list(set(allowed_company_fields + ["name", "domain"])),
                    )
                    current_company_props = comp.properties or {}
                    current_company_name_from_deal = current_company_props.get("name")
                except Exception:
                    pass

        if skip_deal:
            pass  # no deal field proposals
        elif is_new_deal:
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
                    object_type="deals",
                ))
        else:
            selected_deal = next(
                (d for d in matched_deals if d.deal_id == selected_deal_id),
                None
            )
            current_props: dict = {}

            if not selected_deal:
                try:
                    deal = await self.deals.get(selected_deal_id, properties=preview_fields)
                    current_props = deal.properties or {}
                    company_name = None
                    contact_name = None
                    if self.associations and self.company_service:
                        try:
                            cids = await self.associations.get_associations("deals", selected_deal_id, "companies")
                            if cids:
                                comp = await self.company_service.get(
                                    cids[0], properties=list(set(allowed_company_fields + ["name", "domain"]))
                                )
                                current_company_props = comp.properties or {}
                                company_name = current_company_props.get("name")
                        except Exception:
                            pass
                    contact_email = None
                    if self.associations and self.contact_service:
                        try:
                            ctids = await self.associations.get_associations("deals", selected_deal_id, "contacts")
                            if ctids:
                                contact = await self.contact_service.get(
                                    ctids[0],
                                    properties=list(
                                        set(
                                            allowed_contact_fields
                                            + ["email", "firstname", "lastname", "phone", "jobtitle"]
                                        )
                                    ),
                                )
                                current_contact_props = contact.properties or {}
                                cp = current_contact_props
                                contact_name = f"{cp.get('firstname', '')} {cp.get('lastname', '')}".strip() or None
                                contact_email = cp.get("email")
                        except Exception:
                            pass
                    current_contact_name_from_deal = contact_name
                    current_company_name_from_deal = company_name
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
            elif selected_deal:
                try:
                    deal = await self.deals.get(selected_deal_id, properties=preview_fields)
                    current_props = deal.properties or {}
                    if self.associations and self.company_service:
                        try:
                            cids = await self.associations.get_associations("deals", selected_deal_id, "companies")
                            if cids:
                                comp = await self.company_service.get(
                                    cids[0], properties=list(set(allowed_company_fields + ["name", "domain"]))
                                )
                                current_company_props = comp.properties or {}
                                current_company_name_from_deal = current_company_props.get("name")
                        except Exception:
                            pass
                    if self.associations and self.contact_service:
                        try:
                            ctids = await self.associations.get_associations("deals", selected_deal_id, "contacts")
                            if ctids:
                                contact = await self.contact_service.get(
                                    ctids[0],
                                    properties=list(
                                        set(
                                            allowed_contact_fields
                                            + ["email", "firstname", "lastname", "phone", "jobtitle"]
                                        )
                                    ),
                                )
                                current_contact_props = contact.properties or {}
                                cp = current_contact_props
                                current_contact_name_from_deal = f"{cp.get('firstname', '')} {cp.get('lastname', '')}".strip() or None
                        except Exception:
                            pass
                except Exception:
                    pass

            if selected_deal and current_props:
                filtered_properties = drop_call_unsafe_props(
                    filtered_properties,
                    existing_record=True,
                    current=current_props,
                    object_type="deals",
                )
                for field_name, new_value in filtered_properties.items():
                    if new_value is None or new_value == "":
                        continue
                    if field_name == "dealname" and not is_new_deal:
                        continue

                    current_value = current_props.get(field_name)
                    # For description, append only when content is new (same as sync merge)
                    if field_name == "description" and current_value:
                        merged_desc = merge_description(current_value, new_value)
                        if merged_desc is None:
                            continue
                        new_display = merged_desc
                    else:
                        new_display = _display_value(field_name, new_value)

                    current_display = _display_value(field_name, current_value)

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
                            object_type="deals",
                        ))

        # Contact identity + allowlisted contact properties
        show_identity_create = is_new_deal and not selected_contact and not skip_deal
        if show_identity_create:
            extracted_contact_name = extraction.contactName or (
                f"Contact at {extraction.companyName}" if extraction.companyName else None
            )
            if extracted_contact_name:
                proposed_updates.insert(0, ProposedUpdate(
                    field_name="contact_name",
                    field_label="Contact Name",
                    current_value=None,
                    new_value=extracted_contact_name,
                    extraction_confidence=extraction.confidence.get("fields", {}).get("contactName", 0.8),
                    object_type="contacts",
                ))
            if extraction.companyName:
                proposed_updates.insert(0, ProposedUpdate(
                    field_name="company_name",
                    field_label="Company",
                    current_value=None,
                    new_value=extraction.companyName,
                    extraction_confidence=extraction.confidence.get("fields", {}).get("companyName", 0.8),
                    object_type="companies",
                ))

        has_existing_contact = bool(selected_contact) or (bool(selected_deal_id) and not is_new_deal)
        identity_props = (
            self.contact_service.map_extraction_to_properties(extraction)
            if self.contact_service else {}
        )
        contact_props = contact_properties_from_extraction(
            extraction,
            allowed_fields=allowed_contact_fields,
            identity_props=identity_props,
        )
        if has_existing_contact:
            contact_props = drop_call_unsafe_props(
                contact_props,
                existing_record=True,
                current=current_contact_props,
                object_type="contacts",
            )
        for field_name, new_value in contact_props.items():
            if is_identity_name_field(field_name):
                continue
            if field_name == "email" and show_identity_create:
                continue  # shown via new_contact
            new_display = _display_value(field_name, new_value)
            if not new_display:
                continue
            current_display = _display_value(field_name, current_contact_props.get(field_name))
            if has_existing_contact and current_display == new_display:
                continue
            key = f"contacts:{field_name}"
            spec = field_specs_map.get(key, {})
            label = field_labels.get(key, field_name.replace("_", " ").title())
            proposed_updates.append(ProposedUpdate(
                field_name=field_name,
                field_label=label,
                current_value=(current_display or "(empty)") if has_existing_contact else None,
                new_value=new_display,
                extraction_confidence=extraction.confidence.get("fields", {}).get(field_name, 0.7),
                field_type=spec.get("type"),
                options=spec.get("options"),
                object_type="contacts",
            ))

        has_existing_company = bool(current_company_props) or (
            bool(selected_deal_id) and not is_new_deal
        )
        company_props = company_properties_from_extraction(
            extraction,
            allowed_fields=allowed_company_fields,
            identity_props=(
                self.company_service.map_extraction_to_properties(extraction)
                if self.company_service else {}
            ),
        )
        if has_existing_company:
            company_props = drop_call_unsafe_props(
                company_props,
                existing_record=True,
                current=current_company_props,
                object_type="companies",
            )
        for field_name, new_value in company_props.items():
            if field_name == "name" and show_identity_create:
                continue
            new_display = _display_value(field_name, new_value)
            if not new_display:
                continue
            current_display = _display_value(field_name, current_company_props.get(field_name))
            if has_existing_company and (current_display == new_display or field_name == "name"):
                continue
            key = f"companies:{field_name}"
            spec = field_specs_map.get(key, {})
            label = field_labels.get(key, field_name.replace("_", " ").title())
            proposed_updates.append(ProposedUpdate(
                field_name=field_name,
                field_label=label,
                current_value=(current_display or "(empty)") if has_existing_company else None,
                new_value=new_display,
                extraction_confidence=extraction.confidence.get("fields", {}).get(field_name, 0.7),
                field_type=spec.get("type"),
                options=spec.get("options"),
                object_type="companies",
            ))

        # Line items (create proposals) — deal-scoped
        if not skip_deal:
            for i, item in enumerate(line_items_from_extraction(extraction, allowed_line_item_fields)):
                name = item.get("name") or f"Line item {i + 1}"
                qty = item.get("quantity", "")
                price = item.get("price", "")
                summary = f"{name}"
                if qty != "" or price != "":
                    summary = f"{name} · qty {qty} · {price}"
                proposed_updates.append(ProposedUpdate(
                    field_name=f"line_item_{i}",
                    field_label=name,
                    current_value=None,
                    new_value=summary,
                    extraction_confidence=0.7,
                    object_type="line_items",
                ))

        # Available deal fields not yet proposed
        # Deal stage is inferred for every memo and should remain prominent in review.
        for i, update in enumerate(proposed_updates):
            if update.field_name == "dealstage":
                proposed_updates.insert(0, proposed_updates.pop(i))
                break

        # Fields the user can still add manually (allowlisted but not yet proposed).
        # Include contacts/companies so dashboard review can edit those objects too —
        # not only deal properties. Line items stay proposal-only (array create path).
        proposed_keys = {
            f"{(u.object_type or 'deals')}:{u.field_name}"
            for u in proposed_updates
            if not u.field_name.startswith("next_step_task_")
            and not u.field_name.startswith("line_item_")
        }
        available_fields_list: list[AvailableField] = []
        object_field_sources = (
            [("contacts", allowed_contact_fields), ("companies", allowed_company_fields)]
            if skip_deal
            else [
                ("deals", allowed_fields),
                ("contacts", allowed_contact_fields),
                ("companies", allowed_company_fields),
            ]
        )
        for object_type, names in object_field_sources:
            for name in names:
                if f"{object_type}:{name}" in proposed_keys:
                    continue
                # Identity labels already covered by contact_name / company_name rows
                if object_type == "companies" and name == "name":
                    continue
                # Existing contacts keep their CRM name — don't offer firstname/lastname as addable updates
                if has_existing_contact and object_type == "contacts" and is_identity_name_field(name):
                    continue
                spec = field_specs_map.get(f"{object_type}:{name}") or (
                    field_specs_map.get(name, {}) if object_type == "deals" else {}
                )
                available_fields_list.append(AvailableField(
                    name=name,
                    label=spec.get("label", name.replace("_", " ").title()),
                    type=spec.get("type", "string"),
                    options=spec.get("options"),
                    object_type=object_type,
                ))

        new_contact = None
        new_company = None
        if is_new_deal and not selected_contact:
            from .contact_identity import real_contact_email_or_none

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
            selected_contact=selected_contact,
            contact_candidates=list(contact_candidates or []),
            skip_deal=skip_deal,
            proposed_updates=proposed_updates,
            available_fields=available_fields_list,
            allowed_deal_fields=list(allowed_fields),
            allowed_contact_fields=list(allowed_contact_fields),
            allowed_company_fields=list(allowed_company_fields),
            allowed_line_item_fields=list(allowed_line_item_fields),
            new_contact=new_contact,
            new_company=new_company,
        )
