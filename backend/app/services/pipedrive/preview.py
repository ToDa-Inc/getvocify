"""Approval preview for Pipedrive (shared ApprovalPreview shape)."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.models.approval import ApprovalPreview, AvailableField, ContactMatch, DealMatch, ProposedUpdate
from app.models.memo import MemoExtraction
from app.services.extraction_policy import drop_call_unsafe_props
from app.services.hubspot.contact_identity import real_contact_email_or_none
from app.services.hubspot.preview import include_extracted_field, preview_field_already_applied

from .schema import (
    PipedriveSchemaService,
    company_write_props,
    contact_write_props,
    flatten_record,
)
from .search import PipedriveSearchService, primary_email, primary_phone

DEFAULT_DEAL_FIELDS = ["title", "value", "currency", "expected_close_date", "stage_id"]


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def _display_prop(field_name: str, value: Any) -> str:
    """Person emails/phones are v2 arrays. Show the primary value, same as the record."""
    if field_name == "emails":
        if isinstance(value, list):
            return primary_email({"emails": value})
        return _fmt(value)
    if field_name == "phones":
        if isinstance(value, list):
            return primary_phone({"phones": value}) or ""
        return _fmt(value)
    return _fmt(value)


def _new_deal_title(extraction: MemoExtraction) -> str:
    if extraction.companyName:
        return extraction.companyName
    if extraction.contactName:
        return extraction.contactName
    from datetime import date

    return f"Vocify memo {date.today().isoformat()}"


class PipedrivePreviewService:
    def __init__(self, search: PipedriveSearchService, schema: PipedriveSchemaService) -> None:
        self.search = search
        self.schema = schema

    async def _specs(self, names: list[str], object_type: str) -> list[dict[str, Any]]:
        if not names:
            return []
        try:
            return await self.schema.get_curated_field_specs(list(names), object_type)
        except Exception:
            return []

    def _append_object_updates(
        self,
        proposed_updates: list[ProposedUpdate],
        extraction: MemoExtraction,
        props: dict[str, Any],
        specs: dict[str, dict],
        current: dict[str, Any],
        *,
        object_type: str,
        has_existing: bool,
        include_unchanged: bool,
    ) -> None:
        fields = dict(props)
        if has_existing:
            fields = drop_call_unsafe_props(
                fields,
                existing_record=True,
                current=current,
                object_type=object_type,
            )
        for field_name, new_value in fields.items():
            new_display = _display_prop(field_name, new_value)
            current_display = _display_prop(field_name, current.get(field_name)) if has_existing else ""
            if has_existing:
                if not include_extracted_field(
                    new_display=new_display,
                    current_display=current_display,
                    include_unchanged=include_unchanged,
                ):
                    continue
            elif not new_display:
                continue
            spec = specs.get(field_name, {})
            proposed_updates.append(
                ProposedUpdate(
                    field_name=field_name,
                    field_label=spec.get("label", field_name),
                    current_value=(current_display or "(empty)") if has_existing else None,
                    new_value=new_display,
                    extraction_confidence=extraction.confidence.get("fields", {}).get(field_name, 0.7),
                    field_type=spec.get("type"),
                    options=spec.get("options"),
                    object_type=object_type,
                    already_applied=has_existing and preview_field_already_applied(
                        current_display=current_display,
                        new_display=new_display,
                        include_unchanged=include_unchanged,
                    ),
                )
            )

    async def build_preview(
        self,
        memo_id: UUID,
        transcript: str,
        extraction: MemoExtraction,
        matched_deals: list[DealMatch],
        selected_deal_id: Optional[str],
        allowed_fields: Optional[list[str]],
        allowed_contact_fields: Optional[list[str]] = None,
        allowed_company_fields: Optional[list[str]] = None,
        allowed_line_item_fields: Optional[list[str]] = None,
        default_stage_name: Optional[str] = None,
        default_pipeline_id: Optional[str] = None,
        default_stage_id: Optional[str] = None,
        selected_contact: Optional[Any] = None,
        contact_candidates: Optional[Any] = None,
        include_unchanged: bool = False,
        skip_deal: bool = False,
    ) -> ApprovalPreview:
        if allowed_fields is None:
            allowed_fields = list(DEFAULT_DEAL_FIELDS)
        allowed_contact_fields = allowed_contact_fields or ["name", "emails", "phones"]
        allowed_company_fields = allowed_company_fields or ["name"]
        allowed_line_item_fields = allowed_line_item_fields or []

        transcript_summary = transcript[:200] + "..." if len(transcript) > 200 else transcript
        is_new_deal = not skip_deal and not selected_deal_id
        selected_deal: Optional[DealMatch] = None
        proposed_updates: list[ProposedUpdate] = []

        contact_match = selected_contact if isinstance(selected_contact, ContactMatch) else None
        candidates = list(contact_candidates or [])

        if not skip_deal:
            stage_id = await self.schema.resolve_stage_id(
                extraction.dealStage, default_stage_id, default_pipeline_id
            )
            if not stage_id and default_stage_name:
                stage_id = await self.schema.resolve_stage_id(
                    default_stage_name, None, default_pipeline_id
                )
            title = _new_deal_title(extraction) if is_new_deal else None
            mapped = self.schema.map_extraction_to_deal_fields(
                extraction, title=title, stage_id=stage_id, pipeline_id=default_pipeline_id
            )
            filtered = {k: v for k, v in mapped.items() if k in allowed_fields or (is_new_deal and k == "title")}
            field_specs = await self.schema.get_curated_field_specs(allowed_fields)
            field_labels = {s["name"]: s["label"] for s in field_specs}
            field_specs_map = {s["name"]: s for s in field_specs}

            current: dict[str, Any] = {}
            if selected_deal_id:
                selected_deal = next((d for d in matched_deals if d.deal_id == selected_deal_id), None)
                try:
                    current = await self.search.get_deal(selected_deal_id)
                except Exception:
                    current = {}
                if not selected_deal and current:
                    selected_deal = DealMatch(
                        deal_id=selected_deal_id,
                        deal_name=current.get("title") or "Deal",
                        company_name=current.get("org_name"),
                        match_reason="Manual Selection",
                        match_confidence=1.0,
                        stage=str(current.get("stage_id")) if current.get("stage_id") is not None else None,
                        amount=str(current["value"]) if current.get("value") is not None else None,
                        last_updated=str(current.get("update_time") or ""),
                    )

            for field_name, new_value in filtered.items():
                if new_value is None or new_value == "":
                    continue
                if not is_new_deal and field_name == "title":
                    continue
                cur = current.get(field_name)
                new_disp = _fmt(new_value)
                cur_disp = _fmt(cur)
                if not is_new_deal and cur_disp == new_disp:
                    continue
                spec = field_specs_map.get(field_name, {})
                proposed_updates.append(
                    ProposedUpdate(
                        field_name=field_name,
                        field_label=field_labels.get(field_name, field_name),
                        current_value=None if is_new_deal else (cur_disp or "(empty)"),
                        new_value=new_disp,
                        extraction_confidence=extraction.confidence.get("fields", {}).get(field_name, 0.7),
                        field_type=spec.get("type"),
                        options=spec.get("options"),
                        object_type="deals",
                    )
                )

        if extraction.companyName:
            proposed_updates.insert(
                0,
                ProposedUpdate(
                    field_name="name",
                    field_label="Organization",
                    current_value=None,
                    new_value=extraction.companyName,
                    extraction_confidence=extraction.confidence.get("fields", {}).get("companyName", 0.8),
                    object_type="companies",
                ),
            )
        email = real_contact_email_or_none(extraction.contactEmail)
        name = (extraction.contactName or "").strip() or None
        phone = (extraction.contactPhone or "").strip() or None
        if name or email or phone:
            label_bits = [b for b in (name, email, phone) if b]
            proposed_updates.insert(
                0 if extraction.companyName else 0,
                ProposedUpdate(
                    field_name="name",
                    field_label="Person",
                    current_value=None,
                    new_value=" · ".join(label_bits),
                    extraction_confidence=extraction.confidence.get("fields", {}).get("contactName", 0.8),
                    object_type="contacts",
                ),
            )

        contact_specs = {s["name"]: s for s in await self._specs(allowed_contact_fields, "contacts")}
        company_specs = {s["name"]: s for s in await self._specs(allowed_company_fields, "companies")}
        current_contact: dict[str, Any] = {}
        if contact_match is not None:
            try:
                current_contact = flatten_record(await self.search.get_person(contact_match.contact_id))
            except Exception:
                current_contact = {}
        self._append_object_updates(
            proposed_updates,
            extraction,
            contact_write_props(extraction, allowed_contact_fields),
            contact_specs,
            current_contact,
            object_type="contacts",
            has_existing=contact_match is not None,
            include_unchanged=include_unchanged,
        )

        has_existing_company = bool(contact_match and contact_match.company_id)
        current_company: dict[str, Any] = {}
        if has_existing_company and contact_match is not None and contact_match.company_id:
            try:
                current_company = flatten_record(await self.search.get_organization(contact_match.company_id))
            except Exception:
                current_company = {}
        self._append_object_updates(
            proposed_updates,
            extraction,
            company_write_props(extraction, allowed_company_fields),
            company_specs,
            current_company,
            object_type="companies",
            has_existing=has_existing_company,
            include_unchanged=include_unchanged,
        )

        for i, step in enumerate(extraction.nextSteps or []):
            if not str(step).strip():
                continue
            proposed_updates.append(
                ProposedUpdate(
                    field_name=f"next_step_task_{i}",
                    field_label="Next step",
                    current_value=None,
                    new_value=str(step).strip(),
                    extraction_confidence=extraction.confidence.get("fields", {}).get("nextSteps", 0.8),
                    object_type="task",
                )
            )

        # Same objects as HubSpot preview: deals + people, or people only when the
        # page is a person. Organizations join when that person has an org, or when
        # the extraction names one. hs_lead_status is HubSpot-only and is not added.
        proposed_keys = {
            f"{u.object_type or 'deals'}:{u.field_name}"
            for u in proposed_updates
            if not str(u.field_name).startswith("next_step_task_")
        }
        include_companies = has_existing_company or bool((extraction.companyName or "").strip())
        object_field_sources: list[tuple[str, list[str]]] = (
            [("contacts", list(allowed_contact_fields))]
            if skip_deal
            else [("deals", list(allowed_fields)), ("contacts", list(allowed_contact_fields))]
        )
        if include_companies:
            object_field_sources.append(("companies", list(allowed_company_fields)))
        spec_maps = {
            "deals": {s["name"]: s for s in await self._specs(allowed_fields, "deals")} if not skip_deal else {},
            "contacts": contact_specs,
            "companies": company_specs,
        }
        available_fields_list: list[AvailableField] = []
        for object_type, names in object_field_sources:
            specs_map = spec_maps.get(object_type, {})
            for name_f in names:
                if f"{object_type}:{name_f}" in proposed_keys:
                    continue
                spec = specs_map.get(name_f, {})
                available_fields_list.append(
                    AvailableField(
                        name=name_f,
                        label=spec.get("label", name_f),
                        type=spec.get("type", "string"),
                        options=spec.get("options"),
                        object_type=object_type,
                    )
                )

        new_contact = None
        new_company = None
        if not contact_match and (name or email or phone):
            new_contact = {"name": name, "email": email, "phone": phone}
        if extraction.companyName:
            new_company = {"name": extraction.companyName}

        return ApprovalPreview(
            memo_id=memo_id,
            transcript_summary=transcript_summary,
            transcript=transcript or None,
            matched_deals=matched_deals,
            selected_deal=selected_deal,
            is_new_deal=is_new_deal,
            selected_contact=contact_match,
            contact_candidates=candidates,
            skip_deal=skip_deal,
            proposed_updates=proposed_updates,
            available_fields=available_fields_list,
            allowed_deal_fields=allowed_fields,
            allowed_contact_fields=allowed_contact_fields,
            allowed_company_fields=allowed_company_fields,
            allowed_line_item_fields=allowed_line_item_fields,
            new_contact=new_contact,
            new_company=new_company,
        )
