"""Approval preview for Pipedrive (shared ApprovalPreview shape)."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.models.approval import ApprovalPreview, AvailableField, ContactMatch, DealMatch, ProposedUpdate
from app.models.memo import MemoExtraction
from app.services.deal_stage_confirm import suggested_stage
from app.services.hubspot.contact_identity import real_contact_email_or_none

from .schema import PipedriveSchemaService
from .search import PipedriveSearchService

DEFAULT_DEAL_FIELDS = ["title", "value", "currency", "expected_close_date", "stage_id"]


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


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
        stage_confirm: bool = False,
        meeting_booked_stage: Optional[dict[str, str]] = None,
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

            if stage_confirm:
                filtered.pop("stage_id", None)
                stage_row = await self._confirmed_stage_row(
                    extraction,
                    current=current,
                    is_new_deal=is_new_deal,
                    new_deal_stage_id=stage_id,
                    default_pipeline_id=default_pipeline_id,
                    meeting_booked_stage=meeting_booked_stage,
                    label=field_labels.get("stage_id", "Stage"),
                )
                if stage_row:
                    proposed_updates.append(stage_row)

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

        proposed_field_names = {
            u.field_name for u in proposed_updates if u.object_type == "deals" and u.field_name in allowed_fields
        }
        available_fields_list: list[AvailableField] = []
        if not skip_deal:
            specs = await self.schema.get_curated_field_specs(allowed_fields)
            specs_map = {s["name"]: s for s in specs}
            for name_f in allowed_fields:
                if name_f not in proposed_field_names:
                    spec = specs_map.get(name_f, {})
                    available_fields_list.append(
                        AvailableField(
                            name=name_f,
                            label=spec.get("label", name_f),
                            type=spec.get("type", "string"),
                            options=spec.get("options"),
                            object_type="deals",
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
            extraction_confidence=extraction.confidence.get("fields", {}).get("stage_id", 0.7),
            field_type="enumeration",
            options=options,
            object_type="deals",
        )
