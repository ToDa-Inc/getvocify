"""Approval preview for Pipedrive (shared ApprovalPreview shape)."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.models.approval import ApprovalPreview, AvailableField, ContactMatch, DealMatch, ProposedUpdate
from app.models.memo import MemoExtraction
from app.services.deal_stage_confirm import suggested_stage
from app.services.extraction_confidence import field_extraction_confidence
from app.services.hubspot.contact_identity import real_contact_email_or_none

from .object_properties import (
    company_properties_from_extraction,
    contact_properties_from_extraction,
    deal_properties_from_extraction,
)
from .schema import PipedriveSchemaService, flatten_record, props_changed_from_record
from .search import PipedriveSearchService, primary_email, primary_phone

DEFAULT_DEAL_FIELDS = ["title", "value", "currency", "expected_close_date", "stage_id"]


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        parts = []
        for item in v:
            if isinstance(item, dict):
                parts.append(str(item.get("value") or item.get("label") or item))
            else:
                parts.append(str(item))
        return ", ".join(p for p in parts if p)
    return str(v)


def _display_prop(field_name: str, value: Any, spec: dict) -> str:
    if value is None or value == "":
        return ""
    options = spec.get("options") or []
    if options and not isinstance(value, list):
        raw = str(value)
        for opt in options:
            if isinstance(opt, dict) and str(opt.get("value")) == raw:
                return str(opt.get("label") or raw)
        return raw
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

    async def _specs(self, names: list[str], object_type: str) -> tuple[list[dict], dict[str, dict], dict[str, str]]:
        specs = await self.schema.get_curated_field_specs(names, object_type)
        spec_map = {s["name"]: s for s in specs}
        labels = {s["name"]: s.get("label", s["name"]) for s in specs}
        return specs, spec_map, labels

    def _append_object_updates(
        self,
        proposed_updates: list[ProposedUpdate],
        *,
        extraction: MemoExtraction,
        props: dict[str, Any],
        current: dict[str, Any],
        spec_map: dict[str, dict],
        labels: dict[str, str],
        object_type: str,
        include_unchanged: bool,
    ) -> None:
        flat_current = flatten_record(current)
        changed = props_changed_from_record(
            props,
            flat_current,
            include_unchanged=include_unchanged,
        )
        for field_name, new_value in changed.items():
            spec = spec_map.get(field_name, {})
            new_disp = _display_prop(field_name, new_value, spec)
            cur_disp = _display_prop(field_name, flat_current.get(field_name), spec)
            if not new_disp:
                continue
            proposed_updates.append(
                ProposedUpdate(
                    field_name=field_name,
                    field_label=labels.get(field_name, field_name),
                    current_value=cur_disp or "(empty)",
                    new_value=new_disp,
                    extraction_confidence=field_extraction_confidence(extraction, field_name),
                    field_type=spec.get("type"),
                    options=spec.get("options"),
                    object_type=object_type,
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
        skip_deal: bool = False,
        include_unchanged: bool = False,
        stage_confirm: bool = False,
        meeting_booked_stage: Optional[dict[str, str]] = None,
        commitment_tasks: Optional[list] = None,
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

        current_contact: dict[str, Any] = {}
        current_company: dict[str, Any] = {}
        if contact_match:
            try:
                current_contact = await self.search.get_person(contact_match.contact_id)
            except Exception:
                current_contact = {}
            org_id = contact_match.company_id or current_contact.get("org_id")
            if org_id:
                try:
                    current_company = await self.search.get_organization(str(org_id))
                except Exception:
                    current_company = {}

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
                extraction,
                title=title,
                stage_id=stage_id,
                pipeline_id=default_pipeline_id,
            )
            deal_props = deal_properties_from_extraction(extraction, mapped, allowed_fields)
            _, deal_spec_map, deal_labels = await self._specs(allowed_fields, "deals")

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
                if not current_contact and current.get("person_id"):
                    try:
                        current_contact = await self.search.get_person(str(current["person_id"]))
                    except Exception:
                        pass
                if not current_company and current.get("org_id"):
                    try:
                        current_company = await self.search.get_organization(str(current["org_id"]))
                    except Exception:
                        pass

            if stage_confirm:
                # The stage is chosen from the deal's own pipeline (F14), not written as a plain field.
                deal_props.pop("stage_id", None)
                stage_row = await self._confirmed_stage_row(
                    extraction,
                    current=current,
                    is_new_deal=is_new_deal,
                    new_deal_stage_id=stage_id,
                    default_pipeline_id=default_pipeline_id,
                    meeting_booked_stage=meeting_booked_stage,
                    label=deal_labels.get("stage_id", "Stage"),
                )
                if stage_row:
                    proposed_updates.append(stage_row)

            if is_new_deal:
                for field_name, new_value in deal_props.items():
                    if new_value is None or new_value == "":
                        continue
                    if field_name == "title" and not is_new_deal:
                        continue
                    spec = deal_spec_map.get(field_name, {})
                    proposed_updates.append(
                        ProposedUpdate(
                            field_name=field_name,
                            field_label=deal_labels.get(field_name, field_name),
                            current_value=None,
                            new_value=_display_prop(field_name, new_value, spec),
                            extraction_confidence=field_extraction_confidence(extraction, field_name),
                            field_type=spec.get("type"),
                            options=spec.get("options"),
                            object_type="deals",
                        )
                    )
            else:
                self._append_object_updates(
                    proposed_updates,
                    extraction=extraction,
                    props=deal_props,
                    current=current,
                    spec_map=deal_spec_map,
                    labels=deal_labels,
                    object_type="deals",
                    include_unchanged=include_unchanged,
                )

        email = real_contact_email_or_none(extraction.contactEmail)
        name = (extraction.contactName or "").strip() or None
        phone = (extraction.contactPhone or "").strip() or None
        contact_identity = {}
        if name:
            contact_identity["name"] = name
        if email:
            contact_identity["emails"] = [{"value": email, "primary": True, "label": "work"}]
        if phone:
            contact_identity["phones"] = [{"value": phone, "primary": True, "label": "work"}]

        contact_props = contact_properties_from_extraction(
            extraction,
            allowed_fields=allowed_contact_fields,
            identity_props=contact_identity if not contact_match else None,
        )
        if contact_match and not contact_props and (name or email or phone):
            if name and not current_contact.get("name"):
                contact_props["name"] = name
            if email and not primary_email(current_contact):
                contact_props["emails"] = [{"value": email, "primary": True, "label": "work"}]
            if phone and not primary_phone(current_contact):
                contact_props["phones"] = [{"value": phone, "primary": True, "label": "work"}]

        _, contact_spec_map, contact_labels = await self._specs(allowed_contact_fields, "contacts")
        if contact_props:
            self._append_object_updates(
                proposed_updates,
                extraction=extraction,
                props=contact_props,
                current=current_contact,
                spec_map=contact_spec_map,
                labels=contact_labels,
                object_type="contacts",
                include_unchanged=include_unchanged,
            )

        company_identity = {"name": extraction.companyName} if extraction.companyName else {}
        company_props = company_properties_from_extraction(
            extraction,
            allowed_fields=allowed_company_fields,
            identity_props=company_identity if not current_company.get("name") else None,
        )
        _, company_spec_map, company_labels = await self._specs(allowed_company_fields, "companies")
        if company_props:
            self._append_object_updates(
                proposed_updates,
                extraction=extraction,
                props=company_props,
                current=current_company,
                spec_map=company_spec_map,
                labels=company_labels,
                object_type="companies",
                include_unchanged=include_unchanged,
            )

        if commitment_tasks is not None:
            task_rows = [(task.text, task.due_date, task.commitment_id) for task in commitment_tasks]
        else:
            task_rows = [(str(step).strip(), None, None) for step in extraction.nextSteps or []]
        for i, (text, due_date, commitment_id) in enumerate(task_rows):
            if not text:
                continue
            proposed_updates.append(
                ProposedUpdate(
                    field_name=f"next_step_task_{i}",
                    field_label="Next step",
                    current_value=None,
                    new_value=text,
                    extraction_confidence=field_extraction_confidence(extraction, "nextSteps"),
                    object_type="task",
                    due_date=due_date,
                    commitment_id=commitment_id,
                )
            )

        proposed_keys = {
            (u.object_type or "deals", u.field_name)
            for u in proposed_updates
            if u.field_name and u.object_type in {"deals", "contacts", "companies"}
        }
        available_fields_list: list[AvailableField] = []

        async def _available_for(names: list[str], object_type: str) -> None:
            if not names:
                return
            specs, specs_map, _ = await self._specs(names, object_type)
            current_flat: dict[str, Any] = {}
            if object_type == "deals" and selected_deal_id:
                try:
                    current_flat = flatten_record(await self.search.get_deal(selected_deal_id))
                except Exception:
                    current_flat = {}
            elif object_type == "contacts" and current_contact:
                current_flat = flatten_record(current_contact)
            elif object_type == "companies" and current_company:
                current_flat = flatten_record(current_company)
            for name_f in names:
                if (object_type, name_f) in proposed_keys:
                    continue
                spec = specs_map.get(name_f, {})
                cur = current_flat.get(name_f)
                available_fields_list.append(
                    AvailableField(
                        name=name_f,
                        label=spec.get("label", name_f),
                        type=spec.get("type", "string"),
                        options=spec.get("options"),
                        object_type=object_type,
                        current_value=_display_prop(name_f, cur, spec) or None,
                    )
                )

        if not skip_deal:
            await _available_for(allowed_fields, "deals")
        await _available_for(allowed_contact_fields, "contacts")
        await _available_for(allowed_company_fields, "companies")

        new_contact = None
        new_company = None
        if not contact_match and (name or email or phone):
            new_contact = {"name": name, "email": email, "phone": phone}
        if extraction.companyName and not current_company.get("name"):
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

    async def _confirmed_stage_row(
        self,
        extraction: MemoExtraction,
        *,
        current: dict[str, Any],
        is_new_deal: bool,
        new_deal_stage_id: Optional[str],
        default_pipeline_id: Optional[str],
        meeting_booked_stage: Optional[dict[str, str]],
        label: str,
    ) -> Optional[ProposedUpdate]:
        """The stage row of the deal's own pipeline, preselected per the F14 addendum."""
        if is_new_deal:
            pipeline_id = default_pipeline_id
            current_stage = None
            inferred = new_deal_stage_id
        else:
            pipeline_id = str(current["pipeline_id"]) if current.get("pipeline_id") is not None else None
            current_stage = str(current["stage_id"]) if current.get("stage_id") is not None else None
            inferred = (
                await self.schema.resolve_stage_id(extraction.dealStage, None, pipeline_id)
                if extraction.dealStage
                else None
            )
        stages = await self.schema.list_stages(pipeline_id)
        options = [
            {"value": str(s["id"]), "label": str(s.get("name") or s["id"])}
            for s in stages
            if s.get("id") is not None
        ]
        suggested = suggested_stage(
            pipeline_id=pipeline_id,
            stage_ids=[o["value"] for o in options],
            meeting_booked=meeting_booked_stage,
            inferred=inferred,
            fallback=current_stage,
        )
        if not suggested:
            return None
        return ProposedUpdate(
            field_name="stage_id",
            field_label=label,
            current_value=None if is_new_deal else (current_stage or "(empty)"),
            new_value=suggested,
            extraction_confidence=field_extraction_confidence(extraction, "stage_id"),
            field_type="enumeration",
            options=options,
            object_type="deals",
        )
