"""
Orchestrate MemoExtraction sync to Salesforce (Account, Contact, Opportunity).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional, Union
from uuid import UUID

from supabase import Client

from app.logging_config import DOMAIN_SALESFORCE, log_domain
from app.metrics import inc_pipeline_error, record_sync_duration
from app.models.memo import MemoExtraction
from app.services.crm_updates import CRMUpdatesService
from app.services.deal_merge import DealMergeService
from app.services.hubspot.types import SyncResult

from .accounts import SalesforceAccountService
from .client import SalesforceClient
from .contacts import SalesforceContactService
from .opportunities import SalesforceOpportunityService
from .schema import SalesforceSchemaService
from .search import SalesforceSearchService

logger = logging.getLogger(__name__)

FIELDS_PRESERVED_WHEN_UPDATING = frozenset({"Name"})


class SalesforceSyncService:
    def __init__(
        self,
        client: SalesforceClient,
        supabase: Optional[Client],
        crm_updates: CRMUpdatesService,
    ) -> None:
        self.client = client
        self.supabase = supabase
        self.crm_updates = crm_updates
        self.search = SalesforceSearchService(client)
        self.accounts = SalesforceAccountService(client, self.search)
        self.contacts = SalesforceContactService(client, self.search)
        cid = client.connection_id
        self.schema = SalesforceSchemaService(client, supabase, cid)
        self.opportunities = SalesforceOpportunityService(client, self.schema)

    def _filter_fields(self, fields: dict[str, Any], allowed: list[str]) -> dict[str, Any]:
        return {k: v for k, v in fields.items() if k in allowed}

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
    ) -> SyncResult:
        create_companies = auto_create_companies if auto_create_companies is not None else auto_create_contact_company
        create_contacts = auto_create_contacts if auto_create_contacts is not None else auto_create_contact_company
        if deal_id and not is_new_deal:
            create_companies = False
            create_contacts = False

        if allowed_fields is None:
            allowed_fields = ["Name", "Amount", "CloseDate", "StageName", "Description"]

        result = SyncResult(memo_id=str(memo_id))
        t0 = time.perf_counter()
        account_id: Optional[str] = None
        contact_id: Optional[str] = None

        try:
            if create_companies and extraction.companyName:
                try:
                    account_id = await self.accounts.find_or_create(extraction)
                    if account_id:
                        result.company_id = account_id
                        await self.crm_updates.create_update(
                            memo_id=str(memo_id),
                            user_id=user_id,
                            crm_connection_id=str(connection_id),
                            action_type="upsert_company",
                            resource_type="company",
                            data={"company_id": account_id, "name": extraction.companyName},
                        )
                except Exception as e:
                    inc_pipeline_error(DOMAIN_SALESFORCE, "company_upsert")
                    logger.warning("Salesforce account upsert failed: %s", e)

            raw = extraction.raw_extraction or {}
            company = extraction.companyName or raw.get("companyName")
            contact_name = extraction.contactName or raw.get("contactName")
            contact_email = extraction.contactEmail or raw.get("contactEmail")
            if company and not contact_name and not contact_email:
                contact_name = f"Contact at {company}"
            ext_c = extraction.model_copy(
                update={
                    "companyName": company or extraction.companyName,
                    "contactName": contact_name or extraction.contactName,
                    "contactEmail": contact_email or extraction.contactEmail,
                }
            )

            if create_contacts and (ext_c.contactEmail or ext_c.contactName):
                try:
                    contact_id = await self.contacts.find_or_create(ext_c, account_id)
                    if contact_id:
                        result.contact_id = contact_id
                        await self.crm_updates.create_update(
                            memo_id=str(memo_id),
                            user_id=user_id,
                            crm_connection_id=str(connection_id),
                            action_type="upsert_contact",
                            resource_type="contact",
                            data={"contact_id": contact_id},
                        )
                except Exception as e:
                    logger.warning("Salesforce contact upsert failed: %s", e)

            resolved_stage = await self.schema.resolve_stage_name(extraction.dealStage, default_stage_name)

            if deal_id and not is_new_deal:
                current = await self.opportunities.get(
                    deal_id,
                    field_names=list(set(allowed_fields + ["Name", "Amount", "CloseDate", "Description", "StageName"])),
                )
                existing_name = (current.get("Name") or "").strip().lower()
                generic = ("new deal", "nuevo deal", "deal", "")
                deal_name_arg = None if existing_name in generic else current.get("Name")
                new_fields = self.opportunities.map_extraction_to_fields(
                    extraction,
                    deal_name=deal_name_arg,
                    stage_name=resolved_stage or current.get("StageName"),
                    account_id=current.get("AccountId") or account_id,
                )
                merge_svc = DealMergeService()
                merged = merge_svc.merge_properties(
                    existing_properties=current,
                    new_properties=new_fields,
                    allowed_fields=allowed_fields,
                    record_name_field="Name",
                )
                merged = self._filter_fields(merged, allowed_fields)
                merged = {k: v for k, v in merged.items() if k not in FIELDS_PRESERVED_WHEN_UPDATING}
                if merged:
                    await self.opportunities.update(deal_id, merged)
                    await self.crm_updates.create_update(
                        memo_id=str(memo_id),
                        user_id=user_id,
                        crm_connection_id=str(connection_id),
                        action_type="update_deal",
                        resource_type="deal",
                        data={"deal_id": deal_id, "updated_fields": list(merged.keys())},
                    )
                result.deal_id = deal_id
                result.deal_name = current.get("Name") or "Opportunity"
            else:
                create_fields = self.opportunities.map_extraction_to_fields(
                    extraction,
                    stage_name=resolved_stage,
                    account_id=account_id,
                )
                create_fields = self._filter_fields(create_fields, allowed_fields + ["AccountId"])
                if "Name" not in create_fields:
                    create_fields["Name"] = self.opportunities.map_extraction_to_fields(
                        extraction, account_id=account_id
                    ).get("Name", "New Deal")
                oid = await self.opportunities.create(create_fields)
                result.deal_id = oid
                result.deal_name = create_fields.get("Name", "Opportunity")
                await self.crm_updates.create_update(
                    memo_id=str(memo_id),
                    user_id=user_id,
                    crm_connection_id=str(connection_id),
                    action_type="create_deal",
                    resource_type="deal",
                    data={"deal_id": oid},
                )

                if contact_id and oid:
                    try:
                        await self.client.post(
                            "/sobjects/OpportunityContactRole/",
                            json_body={
                                "OpportunityId": oid,
                                "ContactId": contact_id,
                                "Role": "Primary Contact",
                            },
                        )
                    except Exception:
                        logger.info("OpportunityContactRole create skipped or failed (non-fatal)")

            result.success = True
            iu = self.client.instance_url.rstrip("/")
            if result.deal_id:
                result.deal_url = f"{iu}/lightning/r/Opportunity/{result.deal_id}/view"

            record_sync_duration(time.perf_counter() - t0, "success")
            return result

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.error_code = "SF_SYNC_FAILED"
            record_sync_duration(time.perf_counter() - t0, "failure")
            inc_pipeline_error(DOMAIN_SALESFORCE, "sync")
            logger.exception("Salesforce sync failed: %s", e)
            return result
