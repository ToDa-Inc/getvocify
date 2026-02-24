"""
Main synchronization orchestrator for HubSpot.

Orchestrates the complete flow of syncing a voice memo extraction
to HubSpot CRM, including creating/updating contacts, companies, deals,
and associations.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
from uuid import UUID

from .client import HubSpotClient
from .exceptions import HubSpotAuthError, HubSpotScopeError, HubSpotError
from .types import SyncResult
from .contacts import HubSpotContactService
from .companies import HubSpotCompanyService
from .deals import HubSpotDealService, HUBSPOT_READ_ONLY_DEAL_PROPERTIES
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
    ) -> SyncResult:
        """
        Sync a voice memo extraction to HubSpot CRM.
        
        Supports both creating new deals and updating existing deals.
        Filters properties based on allowed_fields whitelist.
        Creates a note with the transcript for deal context.
        
        On retry, reuses existing company/contact IDs from previous attempts
        to prevent orphan creation.
        
        Args:
            memo_id: Voice memo ID
            user_id: User ID
            connection_id: CRM connection ID
            extraction: MemoExtraction with extracted data
            deal_id: Optional deal ID to update (None = create new)
            is_new_deal: Whether to create a new deal (if deal_id is None)
            allowed_fields: List of field names AI is allowed to update
            transcript: Full transcript text to add as note on the deal
            
        Returns:
            SyncResult with success status and created/updated object IDs
        """
        result = SyncResult(memo_id=str(memo_id))

        # Resolve HubSpot owner from user profile (match by email)
        hubspot_owner_id = await _get_hubspot_owner_id_for_user(
            self.client, self.supabase, user_id, connection_id
        )
        if hubspot_owner_id:
            logger.info("Resolved HubSpot owner %s for user %s", hubspot_owner_id, user_id)
        else:
            logger.info("No HubSpot owner matched for user %s (add crm.objects.owners.read scope?)", user_id)

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
            # Step 1: Company (if we have company name and auto-create enabled)
            # Note: For update mode, we still create/update company if needed
            if extraction.companyName:
                try:
                    # Reuse existing company ID if available (prevents duplicates on retry)
                    if existing_company_id:
                        company_id = existing_company_id
                        result.company_id = company_id
                    else:
                        company = await self.companies.create_or_update(extraction)
                        if company:
                            company_id = company.id
                            result.company_id = company_id
                            
                            await self.crm_updates.create_update(
                                memo_id=str(memo_id),
                                user_id=user_id,
                                crm_connection_id=str(connection_id),
                                action_type="upsert_company",
                                resource_type="company",
                                data={"company_id": company_id, "name": extraction.companyName},
                            )
                except Exception as e:
                    # Log error but continue
                    await self.crm_updates.create_update(
                        memo_id=str(memo_id),
                        user_id=user_id,
                        crm_connection_id=str(connection_id),
                        action_type="upsert_company",
                        resource_type="company",
                        data={"error": str(e)},
                    )
            
            # Step 2: Contact - ALWAYS create when we have company or contact info
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
            if extraction_for_contact.contactEmail or extraction_for_contact.contactName:
                try:
                    # Reuse existing contact ID if available (prevents duplicates on retry)
                    if existing_contact_id:
                        contact_id = existing_contact_id
                        result.contact_id = contact_id
                    else:
                        contact = await self.contacts.create_or_update(extraction_for_contact)
                        if contact:
                            contact_id = contact.id
                            result.contact_id = contact_id
                            logger.info(
                                "Created/updated contact %s for memo %s (company=%s, name=%s)",
                                contact_id, memo_id,
                                extraction_for_contact.companyName,
                                extraction_for_contact.contactName,
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
                    logger.warning(
                        "Failed to create/update contact for memo %s: %s. "
                        "Extraction had company=%s, contact=%s, email=%s",
                        memo_id, e,
                        extraction_for_contact.companyName,
                        extraction_for_contact.contactName,
                        extraction_for_contact.contactEmail or "(none)",
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
                    new_properties = await self.deals.map_extraction_to_properties_with_stage(
                        extraction,
                        deal_name=existing_props.get("dealname"),
                    )

                    # 3. Merge: analyze existing + new, produce merged properties
                    merge_svc = DealMergeService()
                    merged_properties = await merge_svc.merge_properties(
                        existing_properties=existing_props,
                        new_properties=new_properties,
                        allowed_fields=allowed_fields,
                        transcript=transcript,
                    )

                    # 4. Filter to allowed fields (safety)
                    filtered_properties = self._filter_properties(
                        merged_properties, allowed_fields
                    )

                    if not filtered_properties:
                        # No changes to apply - still success
                        result.deal_id = deal_id
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
                
                deal_id = result.deal_id
                
            except Exception as e:
                # Deal operation failure is critical
                action = "update" if deal_id and not is_new_deal else "create"
                result.error = f"Failed to {action} deal: {str(e)}"
                result.error_code = f"DEAL_{action.upper()}_FAILED"
                
                await self.crm_updates.create_update(
                    memo_id=str(memo_id),
                    user_id=user_id,
                    crm_connection_id=str(connection_id),
                    action_type=f"{action}_deal",
                    resource_type="deal",
                    data={"error": str(e)},
                )
                
                return result
            
            # Step 5: Associate deal → contact, deal → company (always when we have them)
            # Applies to both new deals and existing deals being updated
            if deal_id and contact_id:
                try:
                    await self.associations.associate_deal_to_contact(deal_id, contact_id)
                    logger.info("Associated deal %s to contact %s", deal_id, contact_id)
                except Exception as e:
                    logger.warning(
                        "Failed to associate deal %s to contact %s: %s. "
                        "Ensure crm.objects.contacts.write and crm.objects.deals.write scopes.",
                        deal_id, contact_id, e,
                    )

            if deal_id and company_id:
                try:
                    await self.associations.associate_deal_to_company(deal_id, company_id)
                except Exception as e:
                    logger.warning(
                        "Failed to associate deal %s to company %s: %s",
                        deal_id, company_id, e,
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
                            await self.crm_updates.create_update(
                                memo_id=str(memo_id),
                                user_id=user_id,
                                crm_connection_id=str(connection_id),
                                action_type="create_tasks",
                                resource_type="task",
                                data={"task_ids": task_ids, "count": len(task_ids)},
                            )
                except Exception as e:
                    logger.warning(
                        "Failed to create tasks for deal %s: %s", deal_id, e,
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
                    logger.info("Created transcript note for deal %s", deal_id)
                    await self.crm_updates.create_update(
                        memo_id=str(memo_id),
                        user_id=user_id,
                        crm_connection_id=str(connection_id),
                        action_type="create_note",
                        resource_type="note",
                        data={"deal_id": deal_id},
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to create transcript note for deal %s: %s. "
                        "Ensure crm.objects.notes.write scope.",
                        deal_id, e,
                    )
            
            # Success!
            result.success = True
            
            # Generate deal name and URL for frontend
            if deal_id:
                result.deal_name = extraction.companyName or "New Deal"
                
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
        except HubSpotScopeError as e:
            result.error = f"Missing HubSpot permissions: {e.message}"
            if e.required_scope:
                result.error += f" Required scope: {e.required_scope}"
            result.error_code = "SCOPE_ERROR"
        except HubSpotError as e:
            result.error = f"HubSpot API error: {e.message}"
            result.error_code = "API_ERROR"
        except Exception as e:
            result.error = f"Unexpected error: {str(e)}"
            result.error_code = "UNKNOWN_ERROR"
        
        return result

