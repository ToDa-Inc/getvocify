"""
Main synchronization orchestrator for HubSpot.

Orchestrates the complete flow of syncing a voice memo extraction
to HubSpot CRM, including creating/updating contacts, companies, deals,
and associations.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
from uuid import UUID

from app.logging_config import log_domain, with_timing, DOMAIN_HUBSPOT
from app.metrics import record_sync_duration, inc_pipeline_error

from .client import HubSpotClient
from .exceptions import HubSpotAuthError, HubSpotScopeError, HubSpotError
from .types import SyncResult
from .contacts import HubSpotContactService
from .companies import HubSpotCompanyService
from .deals import HubSpotDealService, HUBSPOT_READ_ONLY_DEAL_PROPERTIES

# When updating an existing deal (e.g. from extension on a known HubSpot deal page),
# never overwrite these fields - they belong to the deal context, not the memo.
FIELDS_PRESERVED_WHEN_UPDATING_EXISTING_DEAL = frozenset({"dealname"})
from .associations import HubSpotAssociationService
from .tasks import HubSpotTasksService, _parse_date_from_text
from app.models.memo import MemoExtraction
from app.services.crm_updates import CRMUpdatesService
from app.services.task_merge import TaskMergeService
from app.services.deal_merge import DealMergeService

logger = logging.getLogger(__name__)


async def _get_hubspot_owner_id_for_user(
    client: HubSpotClient,
    supabase,
    user_id: str,
    connection_id: Union[UUID, str],
) -> Optional[str]:
    """
    Resolve HubSpot owner ID from SaaS user.
    Matches user email (from auth) to HubSpot owner email.
    Caches result in crm_connections.metadata.
    """
    if not supabase:
        return None
    try:
        # Check cache in connection metadata
        conn_result = supabase.table("crm_connections").select("metadata").eq(
            "id", str(connection_id)
        ).single().execute()
        conn_data = conn_result.data if conn_result else None
        if conn_data:
            meta = conn_data.get("metadata") or {}
            cached = meta.get("hubspot_owner_id")
            if cached:
                return str(cached)

        # Get user email from Supabase auth (admin API)
        auth_user = supabase.auth.admin.get_user_by_id(user_id)
        if not auth_user or not getattr(auth_user, "user", None):
            return None
        user = auth_user.user if hasattr(auth_user, "user") else auth_user
        email = (getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)) or ""
        if not email or not str(email).strip():
            return None

        # Fetch HubSpot owners (paginate to find match; requires crm.objects.owners.read)
        email_lower = str(email).strip().lower()
        after = None
        while True:
            params = {"limit": 100}
            if after:
                params["after"] = after
            resp = await client.get("/crm/v3/owners", params=params)
            if not resp or "results" not in resp:
                break
            for owner in resp.get("results", []):
                owner_email = (owner.get("email") or "").strip().lower()
                if owner_email == email_lower:
                    owner_id = str(owner.get("id", ""))
                    if owner_id:
                        meta = (conn_data or {}).get("metadata", {}) or {}
                        supabase.table("crm_connections").update({
                            "metadata": {**meta, "hubspot_owner_id": owner_id}
                        }).eq("id", str(connection_id)).execute()
                        return owner_id
                    break
            paging = resp.get("paging", {}) or {}
            after = (paging.get("next") or {}).get("after")
            if not after:
                break
    except Exception as e:
        err_str = str(e).lower()
        if "403" in err_str or "forbidden" in err_str or "scope" in err_str:
            logger.warning(
                "HubSpot owners API failed (likely missing crm.objects.owners.read scope): %s. "
                "Add this scope to your HubSpot Private App to set deal owner.",
                e,
            )
        else:
            logger.warning("Could not resolve HubSpot owner for user %s: %s", user_id, e)
    return None


class HubSpotSyncService:
    """
    Orchestrates syncing a MemoExtraction to HubSpot CRM.
    
    Flow:
    1. Find or create company (if companyName exists)
    2. Find or create contact (if contactEmail/contactName exists)
    3. Associate contact → company (if both exist)
    4. Create deal (always)
    5. Associate deal → contact, deal → company
    6. Track each step in crm_updates table
    
    Error handling:
    - Each step is tracked independently
    - Partial failures are logged but don't stop the flow
    - Returns SyncResult with success status and created IDs
    """
    
    def __init__(
        self,
        client: HubSpotClient,
        contacts: HubSpotContactService,
        companies: HubSpotCompanyService,
        deals: HubSpotDealService,
        associations: HubSpotAssociationService,
        tasks: HubSpotTasksService,
        crm_updates: CRMUpdatesService,
        supabase=None,
    ):
        self.client = client
        self.contacts = contacts
        self.companies = companies
        self.deals = deals
        self.associations = associations
        self.tasks = tasks
        self.crm_updates = crm_updates
        self.supabase = supabase
    
    def _filter_properties(
        self,
        properties: dict[str, Any],
        allowed_fields: list[str],
    ) -> dict[str, Any]:
        """
        Filter properties to only include allowed fields.
        
        Args:
            properties: Dictionary of HubSpot properties
            allowed_fields: List of allowed field names
            
        Returns:
            Filtered properties dictionary
        """
        return {
            k: v for k, v in properties.items()
            if k in allowed_fields and k not in HUBSPOT_READ_ONLY_DEAL_PROPERTIES
        }
    
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
    ) -> SyncResult:
        """
        Sync a voice memo extraction to HubSpot CRM.
        
        Supports both creating new deals and updating existing deals.
        Filters properties based on allowed_fields whitelist.
        Creates a note with the transcript for deal context.
        
        Company/contact creation is controlled by:
        - auto_create_companies / auto_create_contacts when provided (from crm_configurations)
        - Fallback: auto_create_contact_company for both when the above are None
        
        Args:
            memo_id: Voice memo ID
            user_id: User ID
            connection_id: CRM connection ID
            extraction: MemoExtraction with extracted data
            deal_id: Optional deal ID to update (None = create new)
            is_new_deal: Whether to create a new deal (if deal_id is None)
            allowed_fields: List of field names AI is allowed to update
            transcript: Full transcript text to add as note on the deal
            auto_create_contact_company: Legacy flag; used for both when auto_create_* not provided
            auto_create_companies: If True, create/upsert company (from crm_configurations)
            auto_create_contacts: If True, create/upsert contact (from crm_configurations)
        Returns:
            SyncResult with success status and created/updated object IDs
        """
        create_companies = auto_create_companies if auto_create_companies is not None else auto_create_contact_company
        create_contacts = auto_create_contacts if auto_create_contacts is not None else auto_create_contact_company
        result = SyncResult(memo_id=str(memo_id))
        t0 = time.perf_counter()
        logger.info(
            "🔗 HubSpot sync started",
            extra=log_domain(DOMAIN_HUBSPOT, "sync_started", memo_id=str(memo_id), user_id=user_id, deal_id=deal_id, is_new_deal=is_new_deal),
        )

        # Resolve HubSpot owner from user profile (match by email)
        hubspot_owner_id = await _get_hubspot_owner_id_for_user(
            self.client, self.supabase, user_id, connection_id
        )
        if hubspot_owner_id:
            logger.info(
                "✅ Resolved HubSpot owner",
                extra=log_domain(DOMAIN_HUBSPOT, "owner_resolved", hubspot_owner_id=hubspot_owner_id, user_id=user_id),
            )
        else:
            logger.info(
                "⚠️ No HubSpot owner matched",
                extra=log_domain(DOMAIN_HUBSPOT, "owner_not_matched", user_id=user_id),
            )

        # Default allowed fields if not provided
        if allowed_fields is None:
            allowed_fields = ["dealname", "amount", "description", "closedate"]
        
        # Check for existing company/contact IDs from previous failed attempts
        # This prevents creating duplicates on retry
        existing_company_id = None
        existing_contact_id = None
        
        if self.supabase:
            try:
                # Get previous CRM updates for this memo
                previous_updates = await self.crm_updates.get_memo_updates(str(memo_id))
                
                # Find successful company/contact creations
                for update in previous_updates:
                    if update.get("status") == "success":
                        data = update.get("data", {})
                        if update.get("action_type") == "upsert_company" and "company_id" in data:
                            existing_company_id = data["company_id"]
                        elif update.get("action_type") == "upsert_contact" and "contact_id" in data:
                            existing_contact_id = data["contact_id"]
            except Exception:
                # If we can't check, proceed normally (not critical)
                pass
        
        company_id = existing_company_id
        contact_id = existing_contact_id
        
        try:
            # Step 1: Company (only when crm_config allows and we have company name)
            if create_companies and extraction.companyName:
                try:
                    # Reuse existing company ID if available (prevents duplicates on retry)
                    if existing_company_id:
                        company_id = existing_company_id
                        result.company_id = company_id
                        logger.info(
                            "🔗 Company reused from previous attempt",
                            extra=log_domain(DOMAIN_HUBSPOT, "company_reused", company_id=company_id, memo_id=str(memo_id)),
                        )
                    else:
                        company = await self.companies.create_or_update(extraction)
                        if company:
                            company_id = company.id
                            result.company_id = company_id
                            logger.info(
                                "✅ Company upserted",
                                extra=log_domain(DOMAIN_HUBSPOT, "company_upserted", company_id=company_id, company_name=extraction.companyName),
                            )
                            await self.crm_updates.create_update(
                                memo_id=str(memo_id),
                                user_id=user_id,
                                crm_connection_id=str(connection_id),
                                action_type="upsert_company",
                                resource_type="company",
                                data={"company_id": company_id, "name": extraction.companyName},
                            )
                except Exception as e:
                    inc_pipeline_error(DOMAIN_HUBSPOT, "company_upsert")
                    logger.warning(
                        "⚠️ Company upsert failed",
                        extra=log_domain(DOMAIN_HUBSPOT, "company_failed", memo_id=str(memo_id), error=str(e)),
                    )
                    await self.crm_updates.create_update(
                        memo_id=str(memo_id),
                        user_id=user_id,
                        crm_connection_id=str(connection_id),
                        action_type="upsert_company",
                        resource_type="company",
                        data={"error": str(e)},
                    )
            
            # Step 2: Contact (only when user setting allows)
            # Pull from extraction or raw_extraction (LLM may put in either)
            raw = extraction.raw_extraction or {}
            company = extraction.companyName or raw.get("companyName") or raw.get("company_name")
            contact_name = extraction.contactName or raw.get("contactName") or raw.get("contact_name")
            contact_email = extraction.contactEmail or raw.get("contactEmail") or raw.get("contact_email")
            # Fallback: when we only have company, create "Contact at {company}"
            if company and not contact_name and not contact_email:
                contact_name = f"Contact at {company}"
            extraction_for_contact = extraction.model_copy(
                update={
                    "companyName": company or extraction.companyName,
                    "contactName": contact_name or extraction.contactName,
                    "contactEmail": contact_email or extraction.contactEmail,
                }
            )
            should_create_contact = create_contacts and (
                extraction_for_contact.contactEmail or extraction_for_contact.contactName
            )
            if should_create_contact:
                try:
                    # Reuse existing contact ID if available (prevents duplicates on retry)
                    if existing_contact_id:
                        contact_id = existing_contact_id
                        result.contact_id = contact_id
                        logger.info(
                            "🔗 Contact reused from previous attempt",
                            extra=log_domain(DOMAIN_HUBSPOT, "contact_reused", contact_id=contact_id, memo_id=str(memo_id)),
                        )
                    elif deal_id and not is_new_deal:
                        # UPDATE MODE: Prefer updating deal's existing contact over creating new one
                        try:
                            contact_ids = await self.associations.get_associations("deals", deal_id, "contacts")
                            if contact_ids:
                                primary_contact_id = contact_ids[0]
                                props = self.contacts.map_extraction_to_properties(extraction_for_contact)
                                if props:
                                    await self.contacts.update(primary_contact_id, props)
                                    contact_id = primary_contact_id
                                    result.contact_id = contact_id
                                    logger.info(
                                        "✅ Contact updated (deal association)",
                                        extra=log_domain(DOMAIN_HUBSPOT, "contact_updated", contact_id=primary_contact_id, memo_id=str(memo_id)),
                                    )
                                    await self.crm_updates.create_update(
                                        memo_id=str(memo_id),
                                        user_id=user_id,
                                        crm_connection_id=str(connection_id),
                                        action_type="upsert_contact",
                                        resource_type="contact",
                                        data={"contact_id": primary_contact_id, "email": extraction_for_contact.contactEmail},
                                    )
                        except Exception as e:
                            logger.warning(
                                "⚠️ Failed to update deal contact, will create: %s",
                                e,
                                extra=log_domain(DOMAIN_HUBSPOT, "contact_update_fallback", memo_id=str(memo_id)),
                            )
                        if not contact_id:
                            contact = await self.contacts.create_or_update(extraction_for_contact)
                            if contact:
                                contact_id = contact.id
                                result.contact_id = contact_id
                                logger.info(
                                    "✅ Contact upserted (fallback)",
                                    extra=log_domain(DOMAIN_HUBSPOT, "contact_upserted", contact_id=contact_id, memo_id=str(memo_id)),
                                )
                                await self.crm_updates.create_update(
                                    memo_id=str(memo_id),
                                    user_id=user_id,
                                    crm_connection_id=str(connection_id),
                                    action_type="upsert_contact",
                                    resource_type="contact",
                                    data={"contact_id": contact_id, "email": extraction_for_contact.contactEmail},
                                )
                    else:
                        contact = await self.contacts.create_or_update(extraction_for_contact)
                        if contact:
                            contact_id = contact.id
                            result.contact_id = contact_id
                            logger.info(
                                "✅ Contact upserted",
                                extra=log_domain(DOMAIN_HUBSPOT, "contact_upserted", contact_id=contact_id, memo_id=str(memo_id), company=extraction_for_contact.companyName, contact_name=extraction_for_contact.contactName),
                            )
                            await self.crm_updates.create_update(
                                memo_id=str(memo_id),
                                user_id=user_id,
                                crm_connection_id=str(connection_id),
                                action_type="upsert_contact",
                                resource_type="contact",
                                data={"contact_id": contact_id, "email": extraction_for_contact.contactEmail},
                            )
                except Exception as e:
                    inc_pipeline_error(DOMAIN_HUBSPOT, "contact_upsert")
                    logger.warning(
                        "⚠️ Contact upsert failed",
                        extra=log_domain(DOMAIN_HUBSPOT, "contact_failed", memo_id=str(memo_id), error=str(e), company=extraction_for_contact.companyName, contact=extraction_for_contact.contactName),
                    )
                    await self.crm_updates.create_update(
                        memo_id=str(memo_id),
                        user_id=user_id,
                        crm_connection_id=str(connection_id),
                        action_type="upsert_contact",
                        resource_type="contact",
                        data={"error": str(e)},
                    )
            
            # Step 3: Associate contact → company
            if contact_id and company_id:
                try:
                    await self.associations.associate_contact_to_company(
                        contact_id, company_id
                    )
                except Exception:
                    # Log error but continue (association is not critical)
                    pass
            
            # Step 4: Deal - Create or Update
            try:
                if deal_id and not is_new_deal:
                    # UPDATE MODE: Merge existing deal with new extraction
                    # 1. Fetch current deal properties
                    fetch_props = list(set(
                        allowed_fields + [
                            "dealname", "amount", "closedate", "description", "dealstage"
                        ]
                    ))
                    current_deal = await self.deals.get(deal_id, properties=fetch_props)
                    existing_props = current_deal.properties or {}

                    # 2. Map new extraction to properties (HubSpot format)
                    # Use extraction-based deal name when existing is generic ("New Deal", etc.)
                    existing_dealname = (existing_props.get("dealname") or "").strip().lower()
                    generic_names = ("new deal", "nuevo deal", "deal", "")
                    deal_name_arg = None if existing_dealname in generic_names else existing_props.get("dealname")
                    new_properties = await self.deals.map_extraction_to_properties_with_stage(
                        extraction,
                        deal_name=deal_name_arg,
                    )

                    # 3. Merge: deterministic (user-approved values; no LLM)
                    merge_svc = DealMergeService()
                    merged_properties = merge_svc.merge_properties(
                        existing_properties=existing_props,
                        new_properties=new_properties,
                        allowed_fields=allowed_fields,
                        transcript=transcript,
                    )

                    # 4. Filter to allowed fields (safety)
                    filtered_properties = self._filter_properties(
                        merged_properties, allowed_fields
                    )
                    # Never overwrite deal identity when updating existing deal
                    # (e.g. extension recorded on known HubSpot deal page)
                    filtered_properties = {
                        k: v for k, v in filtered_properties.items()
                        if k not in FIELDS_PRESERVED_WHEN_UPDATING_EXISTING_DEAL
                    }

                    if not filtered_properties:
                        # No changes to apply - still success
                        result.deal_id = deal_id
                        result.deal_name = existing_props.get("dealname") or "Deal"
                    else:
                        # Update deal with merged properties
                        deal = await self.deals.update(
                            deal_id,
                            filtered_properties,
                            hubspot_owner_id=hubspot_owner_id,
                        )
                        result.deal_id = deal.id
                        await self.crm_updates.create_update(
                            memo_id=str(memo_id),
                            user_id=user_id,
                            crm_connection_id=str(connection_id),
                            action_type="update_deal",
                            resource_type="deal",
                            data={
                                "deal_id": deal.id,
                                "updated_fields": list(filtered_properties.keys()),
                            },
                        )
                        logger.info(
                            "✅ Deal updated",
                            extra=log_domain(DOMAIN_HUBSPOT, "deal_updated", deal_id=deal.id, memo_id=str(memo_id), updated_fields=list(filtered_properties.keys())),
                        )
                    result.deal_name = existing_props.get("dealname") or "Deal"
                else:
                    # CREATE MODE: Create new deal
                    deal = await self.deals.create_or_update(
                        extraction,
                        contact_id=contact_id,
                        company_id=company_id,
                        hubspot_owner_id=hubspot_owner_id,
                    )
                    result.deal_id = deal.id
                    
                    await self.crm_updates.create_update(
                        memo_id=str(memo_id),
                        user_id=user_id,
                        crm_connection_id=str(connection_id),
                        action_type="create_deal",
                        resource_type="deal",
                        data={
                            "deal_id": deal.id,
                            "amount": extraction.dealAmount,
                            "stage": extraction.dealStage,
                        },
                    )
                    logger.info(
                        "✅ Deal created",
                        extra=log_domain(DOMAIN_HUBSPOT, "deal_created", deal_id=deal.id, memo_id=str(memo_id), amount=extraction.dealAmount, stage=extraction.dealStage),
                    )
                    result.deal_name = (deal.properties or {}).get("dealname") or extraction.companyName or "Deal"

                deal_id = result.deal_id
                
            except Exception as e:
                action = "update" if deal_id and not is_new_deal else "create"
                result.error = f"Failed to {action} deal: {str(e)}"
                result.error_code = f"DEAL_{action.upper()}_FAILED"
                record_sync_duration(time.perf_counter() - t0, "failure")
                inc_pipeline_error(DOMAIN_HUBSPOT, f"deal_{action}")
                logger.error(
                    "❌ Deal %s failed: %s",
                    action,
                    str(e),
                    extra=log_domain(DOMAIN_HUBSPOT, f"deal_{action}_failed", memo_id=str(memo_id), error=str(e)),
                )
                await self.crm_updates.create_update(
                    memo_id=str(memo_id),
                    user_id=user_id,
                    crm_connection_id=str(connection_id),
                    action_type=f"{action}_deal",
                    resource_type="deal",
                    data={"error": str(e)},
                )
                return result
            
            # Step 4b: UPDATE MODE - Update deal's primary contact when extraction has contact info but no email
            # (create_or_update requires email; deal's contact can still be updated by ID)
            if deal_id and not is_new_deal and (extraction_for_contact.contactName or extraction_for_contact.contactRole or extraction_for_contact.contactPhone):
                if not contact_id:
                    try:
                        contact_ids = await self.associations.get_associations("deals", deal_id, "contacts")
                        if contact_ids:
                            primary_contact_id = contact_ids[0]
                            props = self.contacts.map_extraction_to_properties(extraction_for_contact)
                            props.pop("email", None)
                            if props:
                                await self.contacts.update(primary_contact_id, props)
                                contact_id = primary_contact_id
                                result.contact_id = primary_contact_id
                                logger.info(
                                    "✅ Contact updated (deal association)",
                                    extra=log_domain(DOMAIN_HUBSPOT, "contact_updated", contact_id=primary_contact_id, memo_id=str(memo_id)),
                                )
                    except Exception as e:
                        logger.warning(
                            "⚠️ Failed to update deal contact: %s",
                            e,
                            extra=log_domain(DOMAIN_HUBSPOT, "contact_update_failed", memo_id=str(memo_id), error=str(e)),
                        )

            # Step 5: Associate deal → contact, deal → company (always when we have them)
            # Applies to both new deals and existing deals being updated
            if deal_id and contact_id:
                try:
                    await self.associations.associate_deal_to_contact(deal_id, contact_id)
                    logger.info(
                        "✅ Associations done: deal to contact",
                        extra=log_domain(DOMAIN_HUBSPOT, "associations_done", deal_id=deal_id, contact_id=contact_id),
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to associate deal %s to contact %s: %s. "
                        "Ensure crm.objects.contacts.write and crm.objects.deals.write scopes.",
                        deal_id, contact_id, e,
                    )

            if deal_id and company_id:
                try:
                    await self.associations.associate_deal_to_company(deal_id, company_id)
                    logger.info(
                        "✅ Associations done: deal to company",
                        extra=log_domain(DOMAIN_HUBSPOT, "associations_done", deal_id=deal_id, company_id=company_id),
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to associate deal %s to company %s: %s",
                        deal_id, company_id, e,
                        extra=log_domain(DOMAIN_HUBSPOT, "association_failed", deal_id=deal_id, company_id=company_id),
                    )

            # Step 6: Tasks - merge with existing when updating deal, else create new
            if deal_id and extraction.nextSteps:
                try:
                    used_merge = False
                    if not is_new_deal:
                        # UPDATE MODE: Fetch existing tasks, merge with new extraction
                        existing_tasks = await self.tasks.list_tasks_for_deal(deal_id)
                        if existing_tasks:
                            merge_svc = TaskMergeService()
                            merge_result = await merge_svc.merge_tasks(
                                existing_tasks=existing_tasks,
                                extraction=extraction,
                                transcript=transcript,
                            )
                            created_ids = []
                            # Execute add
                            for add_op in merge_result.add:
                                due = add_op.due_date or _parse_date_from_text(add_op.subject) or (
                                    datetime.now(timezone.utc) + timedelta(days=3)
                                )
                                tid = await self.tasks.create_task(
                                    subject=add_op.subject,
                                    due_date=due,
                                    deal_id=deal_id,
                                    body=extraction.summary or "",
                                    hubspot_owner_id=hubspot_owner_id,
                                )
                                if tid:
                                    created_ids.append(tid)
                            # Execute update
                            for upd_op in merge_result.update:
                                await self.tasks.update_task(
                                    task_id=upd_op.id,
                                    subject=upd_op.subject,
                                    due_date=upd_op.due_date,
                                    hubspot_owner_id=hubspot_owner_id,
                                )
                            # Execute delete
                            for del_id in merge_result.delete:
                                await self.tasks.delete_task(del_id)
                            if created_ids or merge_result.update or merge_result.delete:
                                await self.crm_updates.create_update(
                                    memo_id=str(memo_id),
                                    user_id=user_id,
                                    crm_connection_id=str(connection_id),
                                    action_type="merge_tasks",
                                    resource_type="task",
                                    data={
                                        "task_ids": created_ids,
                                        "updated": [u.id for u in merge_result.update],
                                        "deleted": merge_result.delete,
                                    },
                                )
                            used_merge = True
                    if not used_merge:
                        # CREATE MODE or no existing tasks: create from extraction
                        task_ids = await self.tasks.create_tasks_from_extraction(
                            extraction,
                            deal_id=deal_id,
                            hubspot_owner_id=hubspot_owner_id,
                        )
                        if task_ids:
                            logger.info(
                                "✅ Tasks created",
                                extra=log_domain(DOMAIN_HUBSPOT, "tasks_created", deal_id=deal_id, count=len(task_ids), task_ids=task_ids),
                            )
                            await self.crm_updates.create_update(
                                memo_id=str(memo_id),
                                user_id=user_id,
                                crm_connection_id=str(connection_id),
                                action_type="create_tasks",
                                resource_type="task",
                                data={"task_ids": task_ids, "count": len(task_ids)},
                            )
                except Exception as e:
                    inc_pipeline_error(DOMAIN_HUBSPOT, "create_tasks")
                    logger.warning(
                        "Failed to create tasks for deal %s: %s", deal_id, e,
                        extra=log_domain(DOMAIN_HUBSPOT, "tasks_failed", deal_id=deal_id, error=str(e)),
                    )

            # Step 7: Create note with transcript for deal context
            if deal_id and transcript and transcript.strip():
                try:
                    note_body = transcript.strip()
                    if len(note_body) > 65536:
                        note_body = note_body[:65533] + "..."
                    note_payload = {
                        "properties": {
                            "hs_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "hs_note_body": note_body,
                        },
                        "associations": [
                            {
                                "to": {"id": str(deal_id)},
                                "types": [
                                    {
                                        "associationCategory": "HUBSPOT_DEFINED",
                                        "associationTypeId": 214,
                                    }
                                ]
                            }
                        ]
                    }
                    if hubspot_owner_id:
                        note_payload["properties"]["hubspot_owner_id"] = hubspot_owner_id
                    await self.client.post("/crm/v3/objects/notes", data=note_payload)
                    logger.info(
                        "✅ Note created",
                        extra=log_domain(DOMAIN_HUBSPOT, "note_created", deal_id=deal_id),
                    )
                    await self.crm_updates.create_update(
                        memo_id=str(memo_id),
                        user_id=user_id,
                        crm_connection_id=str(connection_id),
                        action_type="create_note",
                        resource_type="note",
                        data={"deal_id": deal_id},
                    )
                except Exception as e:
                    inc_pipeline_error(DOMAIN_HUBSPOT, "create_note")
                    logger.warning(
                        "Failed to create transcript note for deal %s: %s. "
                        "Ensure crm.objects.notes.write scope.",
                        deal_id, e,
                        extra=log_domain(DOMAIN_HUBSPOT, "note_failed", deal_id=deal_id, error=str(e)),
                    )
            
            # Success!
            result.success = True
            elapsed = time.perf_counter() - t0
            record_sync_duration(elapsed, "success")
            logger.info(
                "✅ HubSpot sync complete",
                extra=log_domain(DOMAIN_HUBSPOT, "sync_complete", memo_id=str(memo_id), deal_id=result.deal_id, company_id=result.company_id, contact_id=result.contact_id, duration_ms=round(elapsed * 1000, 2)),
            )
            
            # Generate deal URL for frontend (deal_name set during create/update)
            if deal_id:
                if not result.deal_name:
                    try:
                        deal_obj = await self.deals.get(deal_id, properties=["dealname"])
                        result.deal_name = (deal_obj.properties or {}).get("dealname") or "Deal"
                    except Exception:
                        result.deal_name = extraction.companyName or "Deal"

                portal_id = None
                region = "na1"
                metadata = {}
                
                # Try connection metadata first
                if self.supabase:
                    conn = self.supabase.table("crm_connections").select("metadata").eq("id", str(connection_id)).single().execute()
                    if conn.data:
                        metadata = conn.data.get("metadata", {}) or {}
                        portal_id = metadata.get("portal_id")
                        region = metadata.get("region", "na1")
                
                # Fallback: fetch portal_id from HubSpot API (e.g. old connections without metadata)
                if not portal_id:
                    try:
                        account_info = await self.client.get("/integrations/v1/me")
                        if account_info:
                            portal_id = str(account_info.get("portalId", ""))
                            # Update connection metadata for future syncs
                            if portal_id and self.supabase:
                                self.supabase.table("crm_connections").update({
                                    "metadata": {**metadata, "portal_id": portal_id, "region": region}
                                }).eq("id", str(connection_id)).execute()
                    except Exception:
                        pass
                
                if portal_id:
                    region_prefix = f"-{region}" if region != "na1" else ""
                    result.deal_url = f"https://app{region_prefix}.hubspot.com/contacts/{portal_id}/record/0-3/{deal_id}"
            
        except HubSpotAuthError as e:
            result.error = f"HubSpot authentication failed: {e.message}"
            result.error_code = "AUTH_ERROR"
            record_sync_duration(time.perf_counter() - t0, "failure")
            inc_pipeline_error(DOMAIN_HUBSPOT, "auth_error")
            logger.error(
                "❌ Sync failed: auth error",
                extra=log_domain(DOMAIN_HUBSPOT, "sync_failed", memo_id=str(memo_id), error=str(e.message)),
            )
        except HubSpotScopeError as e:
            result.error = f"Missing HubSpot permissions: {e.message}"
            if e.required_scope:
                result.error += f" Required scope: {e.required_scope}"
            result.error_code = "SCOPE_ERROR"
            record_sync_duration(time.perf_counter() - t0, "failure")
            inc_pipeline_error(DOMAIN_HUBSPOT, "scope_error")
            logger.error(
                "❌ Sync failed: scope error",
                extra=log_domain(DOMAIN_HUBSPOT, "sync_failed", memo_id=str(memo_id), error=str(e.message)),
            )
        except HubSpotError as e:
            result.error = f"HubSpot API error: {e.message}"
            result.error_code = "API_ERROR"
            record_sync_duration(time.perf_counter() - t0, "failure")
            inc_pipeline_error(DOMAIN_HUBSPOT, "api_error")
            logger.error(
                "❌ Sync failed: API error",
                extra=log_domain(DOMAIN_HUBSPOT, "sync_failed", memo_id=str(memo_id), error=str(e.message)),
            )
        except Exception as e:
            result.error = f"Unexpected error: {str(e)}"
            result.error_code = "UNKNOWN_ERROR"
            record_sync_duration(time.perf_counter() - t0, "failure")
            inc_pipeline_error(DOMAIN_HUBSPOT, "unknown_error")
            logger.exception(
                "❌ Sync failed: unexpected error",
                extra=log_domain(DOMAIN_HUBSPOT, "sync_failed", memo_id=str(memo_id), error=str(e)),
            )
        
        return result

