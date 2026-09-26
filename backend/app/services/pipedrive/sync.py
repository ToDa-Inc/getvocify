"""Orchestrate MemoExtraction writes to Pipedrive (org, person, deal, note, activities)."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Optional, Union
from uuid import UUID

from supabase import Client

from app.logging_config import DOMAIN_PIPEDRIVE, log_domain
from app.metrics import inc_pipeline_error, record_sync_duration
from app.models.memo import MemoExtraction
from app.services.crm_updates import CRMUpdatesService
from app.services.hubspot.contact_identity import real_contact_email_or_none
from app.services.hubspot.types import SyncResult

from .activities import PipedriveActivityService
from .client import PipedriveClient, unwrap_data
from .exceptions import PipedriveError
from .notes import PipedriveNoteService, format_note_content
from .record_urls import build_pipedrive_record_url, company_domain_from_api_domain
from .schema import PipedriveSchemaService
from .search import PipedriveSearchService, primary_email

logger = logging.getLogger(__name__)

DEFAULT_DEAL_FIELDS = ["title", "value", "currency", "expected_close_date", "stage_id"]


def new_deal_title(extraction: MemoExtraction) -> str:
    if extraction.companyName:
        return extraction.companyName
    if extraction.contactName:
        return extraction.contactName
    return f"Vocify memo {date.today().isoformat()}"


def _utc_due(due_at: Optional[datetime]) -> dict[str, str]:
    """Pipedrive activity due date and time, both UTC."""
    if due_at is None:
        return {}
    utc = due_at.astimezone(timezone.utc)
    return {"due_date": utc.date().isoformat(), "due_time": utc.strftime("%H:%M")}


def confirmed_stage_choice(extraction: MemoExtraction) -> Optional[str]:
    """The stage_id row the rep kept on review; absent when the rep removed it."""
    value = (extraction.raw_extraction or {}).get("stage_id")
    text = str(value).strip() if value is not None else ""
    return text or None


class PipedriveSyncService:
    def __init__(
        self,
        client: PipedriveClient,
        supabase: Optional[Client],
        crm_updates: CRMUpdatesService,
    ) -> None:
        self.client = client
        self.supabase = supabase
        self.crm_updates = crm_updates
        self.search = PipedriveSearchService(client)
        cid = client.connection_id
        self.schema = PipedriveSchemaService(client, supabase, cid)
        self.notes = PipedriveNoteService(client)
        self.activities = PipedriveActivityService(client)

    async def sync_memo(
        self,
        memo_id: Union[UUID, str],
        user_id: str,
        connection_id: Union[UUID, str],
        extraction: MemoExtraction,
        deal_id: Optional[str] = None,
        is_new_deal: bool = False,
        allowed_fields: Optional[list[str]] = None,
        transcript: Optional[str] = None,
        auto_create_contact_company: bool = False,
        auto_create_companies: Optional[bool] = None,
        auto_create_contacts: Optional[bool] = None,
        default_stage_name: Optional[str] = None,
        default_pipeline_id: Optional[str] = None,
        default_stage_id: Optional[str] = None,
        create_note: bool = True,
        contact_id: Optional[str] = None,
        company_id: Optional[str] = None,
        skip_deal: bool = False,
        stage_confirm: bool = False,
        commitment_tasks: Optional[list] = None,
    ) -> SyncResult:
        """stage_confirm: the stage is the one the rep confirmed (raw_extraction.stage_id);
        an existing deal's stage is written only when it differs from the current one.
        commitment_tasks (COMMITMENT_TASKS_ENABLED): one activity per commitment, with its date,
        before the nextSteps the rep edited."""
        create_companies = auto_create_companies if auto_create_companies is not None else auto_create_contact_company
        create_contacts = auto_create_contacts if auto_create_contacts is not None else auto_create_contact_company
        if deal_id and not is_new_deal:
            create_companies = False
            create_contacts = False
        if allowed_fields is None:
            allowed_fields = list(DEFAULT_DEAL_FIELDS)

        result = SyncResult(memo_id=str(memo_id))
        t0 = time.perf_counter()
        org_id = company_id
        person_id = contact_id
        landed: list[str] = []
        creating = (not skip_deal) and (is_new_deal or not deal_id)
        stage_id: Optional[str] = None
        confirmed_stage = confirmed_stage_choice(extraction) if stage_confirm else None

        try:
            if not skip_deal:
                stage_id = await self.schema.resolve_stage_id(
                    confirmed_stage or extraction.dealStage, default_stage_id, default_pipeline_id
                )
                if not stage_id and default_stage_name:
                    stage_id = await self.schema.resolve_stage_id(
                        default_stage_name, None, default_pipeline_id
                    )
                if creating and not stage_id:
                    result.success = False
                    result.error = "Pipedrive default pipeline stage is required before creating a deal."
                    result.error_code = "PIPEDRIVE_STAGE_REQUIRED"
                    return result

            if create_companies and extraction.companyName:
                org_id = await self._find_or_create_org(extraction.companyName, org_id)
                if org_id:
                    result.company_id = org_id
                    landed.append("org")
                    await self.crm_updates.create_update(
                        memo_id=str(memo_id),
                        user_id=user_id,
                        crm_connection_id=str(connection_id),
                        action_type="upsert_company",
                        resource_type="company",
                        data={"company_id": org_id, "name": extraction.companyName},
                    )

            email = real_contact_email_or_none(extraction.contactEmail)
            name = (extraction.contactName or "").strip() or None
            phone = (extraction.contactPhone or "").strip() or None
            if create_contacts and (name or email or phone):
                if not name:
                    logger.warning(
                        "Pipedrive person create skipped — name is required",
                        extra=log_domain(DOMAIN_PIPEDRIVE, "person_name_required", memo_id=str(memo_id)),
                    )
                else:
                    person_id = await self._find_or_create_person(
                        name=name, email=email, phone=phone, org_id=org_id, person_id=person_id
                    )
                    if person_id:
                        result.contact_id = person_id
                        landed.append("person")
                        await self.crm_updates.create_update(
                            memo_id=str(memo_id),
                            user_id=user_id,
                            crm_connection_id=str(connection_id),
                            action_type="upsert_contact",
                            resource_type="contact",
                            data={"contact_id": person_id},
                        )

            if not skip_deal:
                title = new_deal_title(extraction) if creating else None
                mapped = self.schema.map_extraction_to_deal_fields(
                    extraction,
                    title=title,
                    stage_id=stage_id,
                    pipeline_id=default_pipeline_id if creating else None,
                    org_id=org_id,
                    person_id=person_id,
                )
                filtered = {k: v for k, v in mapped.items() if k in allowed_fields or k in ("title", "stage_id", "pipeline_id", "org_id", "person_id")}
                if creating:
                    payload = self.schema.split_write_payload(filtered)
                    created = unwrap_data(await self.client.post("/deals", json_body=payload))
                    deal_id = str(created["id"]) if isinstance(created, dict) and created.get("id") is not None else None
                    result.deal_name = (created or {}).get("title") if isinstance(created, dict) else title
                else:
                    current = await self.search.get_deal(deal_id)
                    existing_title = (current.get("title") or "").strip().lower()
                    if existing_title not in ("", "new deal", "nuevo deal", "deal"):
                        filtered.pop("title", None)
                    update_fields = {
                        k: v for k, v in filtered.items() if k in allowed_fields or k in ("org_id", "person_id")
                    }
                    if stage_confirm:
                        update_fields.pop("stage_id", None)
                        new_stage = await self._stage_change(confirmed_stage, current)
                        if new_stage:
                            update_fields["stage_id"] = int(new_stage)
                    payload = self.schema.split_write_payload(update_fields)
                    if payload:
                        await self.client.patch(f"/deals/{deal_id}", json_body=payload)
                    result.deal_name = current.get("title") or title

                if not deal_id:
                    result.success = False
                    result.error = "Pipedrive did not return a deal id."
                    return result
                result.deal_id = deal_id
                landed.append("deal")
                if self.supabase:
                    try:
                        self.supabase.table("memos").update({"matched_deal_id": deal_id}).eq("id", str(memo_id)).execute()
                    except Exception as e:
                        logger.warning("Could not persist matched_deal_id: %s", e)
                await self.crm_updates.create_update(
                    memo_id=str(memo_id),
                    user_id=user_id,
                    crm_connection_id=str(connection_id),
                    action_type="upsert_deal",
                    resource_type="deal",
                    data={"deal_id": deal_id},
                )

            if create_note and (deal_id or person_id or org_id):
                content = format_note_content(summary=extraction.summary, transcript=transcript or "")
                note_id = await self.notes.create(
                    content, deal_id=deal_id, person_id=person_id, org_id=org_id
                )
                if not note_id:
                    result.success = False
                    result.error = "Pipedrive note was not created."
                    result.error_code = "PIPEDRIVE_NOTE_FAILED"
                    return result
                landed.append("note")
                await self.crm_updates.create_update(
                    memo_id=str(memo_id),
                    user_id=user_id,
                    crm_connection_id=str(connection_id),
                    action_type="create_note",
                    resource_type="note",
                    data={"note_id": note_id},
                )

            steps = [s.strip() for s in (extraction.nextSteps or []) if str(s).strip()]
            planned = [(task, task.text, _utc_due(task.due_at)) for task in commitment_tasks or []]
            planned += [(None, step, {}) for step in steps]
            result.tasks_requested_count = len(planned)
            if planned:
                task_type = await self.activities.resolve_task_type()
                if not task_type:
                    result.tasks_warning = "No Pipedrive activity type with key_string/icon_key 'task' — next steps were not written."
                else:
                    created_n = 0
                    for task, subject, due in planned:
                        aid = await self.activities.create_next_step(
                            subject, deal_id=deal_id, person_id=person_id, org_id=org_id, **due
                        )
                        if aid:
                            created_n += 1
                            if task is not None:
                                result.commitment_task_ids[task.commitment_id] = aid
                    result.tasks_created_count = created_n
                    if created_n < len(planned):
                        result.tasks_warning = f"Created {created_n} of {len(planned)} next-step activities."

            result.success = True
            result.company_id = org_id
            result.contact_id = person_id
            domain = company_domain_from_api_domain(getattr(self.client, "api_domain", None))
            if domain and deal_id:
                result.deal_url = build_pipedrive_record_url(domain, "deal", deal_id)
            if domain and person_id:
                result.contact_url = build_pipedrive_record_url(domain, "person", person_id)
            record_sync_duration(time.perf_counter() - t0, "success")
            return result
        except PipedriveError as e:
            inc_pipeline_error(DOMAIN_PIPEDRIVE, "sync")
            result.success = False
            result.error = e.message
            result.error_code = e.error_code or "PIPEDRIVE_SYNC_FAILED"
            record_sync_duration(time.perf_counter() - t0, "failure")
            logger.exception(
                "Pipedrive sync failed: %s",
                e,
                extra=log_domain(DOMAIN_PIPEDRIVE, "sync_failed", memo_id=str(memo_id), landed=landed),
            )
            return result
        except Exception as e:
            inc_pipeline_error(DOMAIN_PIPEDRIVE, "sync")
            result.success = False
            result.error = str(e)
            result.error_code = "PIPEDRIVE_SYNC_FAILED"
            record_sync_duration(time.perf_counter() - t0, "failure")
            logger.exception("Pipedrive sync failed: %s", e)
            return result

    async def _stage_change(self, confirmed_stage: Optional[str], current: dict[str, Any]) -> Optional[str]:
        if not confirmed_stage:
            return None
        pipeline_id = current.get("pipeline_id")
        resolved = await self.schema.resolve_stage_id(
            confirmed_stage, None, str(pipeline_id) if pipeline_id is not None else None
        )
        if not resolved or resolved == str(current.get("stage_id")):
            return None
        return resolved

    async def _find_or_create_org(self, name: str, existing_id: Optional[str]) -> Optional[str]:
        if existing_id:
            return existing_id
        hits = await self.search.search_organizations(name, limit=3)
        needle = name.strip().lower()
        for h in hits:
            if (h.get("name") or "").strip().lower() == needle and h.get("id") is not None:
                return str(h["id"])
        if hits and hits[0].get("id") is not None:
            return str(hits[0]["id"])
        created = unwrap_data(await self.client.post("/organizations", json_body={"name": name}))
        if isinstance(created, dict) and created.get("id") is not None:
            return str(created["id"])
        return None

    async def _find_or_create_person(
        self,
        *,
        name: str,
        email: Optional[str],
        phone: Optional[str],
        org_id: Optional[str],
        person_id: Optional[str],
    ) -> Optional[str]:
        if person_id:
            return person_id
        if email:
            hits = await self.search.search_persons(email, fields="email", limit=5)
            for h in hits:
                if (primary_email(h) or "").lower() == email and h.get("id") is not None:
                    return str(h["id"])
        body: dict[str, Any] = {"name": name}
        if email:
            body["emails"] = [{"value": email, "primary": True, "label": "work"}]
        if phone:
            body["phones"] = [{"value": phone, "primary": True, "label": "work"}]
        if org_id:
            body["org_id"] = int(org_id)
        created = unwrap_data(await self.client.post("/persons", json_body=body))
        if isinstance(created, dict) and created.get("id") is not None:
            return str(created["id"])
        return None
