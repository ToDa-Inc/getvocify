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
from .exceptions import (
    HubSpotAuthError,
    HubSpotScopeError,
    HubSpotError,
    HubSpotValidationError,
    HubSpotNotFoundError,
)
from .types import SyncResult
from .contacts import HubSpotContactService
from .companies import HubSpotCompanyService
from .deals import HubSpotDealService, HUBSPOT_READ_ONLY_DEAL_PROPERTIES
from .call_outcome import CallOutcomeContext, apply_call_outcome
from .account_info import build_deal_record_url, resolve_account_context

# When updating an existing deal (e.g. from extension on a known HubSpot deal page),
# never overwrite these fields - they belong to the deal context, not the memo.
FIELDS_PRESERVED_WHEN_UPDATING_EXISTING_DEAL = frozenset({"dealname"})
from .associations import HubSpotAssociationService
from .tasks import (
    HubSpotTasksService,
    TaskBatchResult,
    _parse_date_from_text,
    _normalize_task_subject,
    format_next_step_task,
    _next_step_schedule_hints,
    summarize_task_batch,
    build_task_body,
)
from app.models.memo import MemoExtraction
from app.services.crm_updates import CRMUpdatesService
from app.services.task_merge import TaskMergeService
from app.services.deal_merge import DealMergeService
from app.services.extraction import _clean_extracted_name
from app.services.extraction_policy import drop_call_unsafe_props
from .object_properties import (
    contact_properties_from_extraction,
    company_properties_from_extraction,
    line_items_from_extraction,
)

logger = logging.getLogger(__name__)


def _contact_props_updating_existing(
    contacts: HubSpotContactService,
    extraction: MemoExtraction,
    allowed_fields: Optional[list[str]],
) -> dict[str, Any]:
    """Map extraction onto an existing contact without renaming them from a spoken name."""
    props = contact_properties_from_extraction(
        extraction,
        allowed_fields=allowed_fields,
        identity_props=contacts.map_extraction_to_properties(extraction),
    )
    return drop_call_unsafe_props(
        props,
        existing_record=True,
        current={},
        object_type="contacts",
    )


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

    async def _resolve_company_id(
        self,
        company_id: Optional[str],
        contact_id: Optional[str],
        deal_id: Optional[str],
    ) -> Optional[str]:
        """Prefer the payload id, then contact→company, then deal→company."""
        if company_id:
            return str(company_id)
        if contact_id:
            try:
                cids = await self.associations.get_associations("contacts", contact_id, "companies")
                if cids:
                    return str(cids[0])
            except Exception:
                pass
        if deal_id:
            try:
                cids = await self.associations.get_associations("deals", deal_id, "companies")
                if cids:
                    return str(cids[0])
            except Exception:
                pass
        return None
    
    async def sync_memo(
        self,
        memo_id: Union[UUID, str],
        user_id: str,
        connection_id: Union[UUID, str],
        extraction: MemoExtraction,
        deal_id: Optional[str] = None,
        is_new_deal: bool = False,
        allowed_fields: Optional[list[str]] = None,
        allowed_contact_fields: Optional[list[str]] = None,
        allowed_company_fields: Optional[list[str]] = None,
        allowed_line_item_fields: Optional[list[str]] = None,
        transcript: Optional[str] = None,
        auto_create_contact_company: bool = False,
        auto_create_companies: Optional[bool] = None,
        auto_create_contacts: Optional[bool] = None,
        default_pipeline_id: Optional[str] = None,
        default_stage_id: Optional[str] = None,
        create_note: bool = True,
        contact_id: Optional[str] = None,
        company_id: Optional[str] = None,
        skip_deal: bool = False,
        call_outcome: Optional[str] = None,
        lost_reason: Optional[str] = None,
        lost_reason_deal_property: Optional[str] = None,
        lost_lead_status_value: Optional[str] = None,
        on_hold_lead_status_value: Optional[str] = None,
    ) -> SyncResult:
        """
        Sync a voice memo extraction to HubSpot CRM.
        
        Supports both creating new deals and updating existing deals.
        Filters properties based on allowed_*_fields whitelists.
        Optionally creates a note with summary + transcript for deal context.
        
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
            allowed_fields: Deal field names AI is allowed to update
            allowed_contact_fields: Contact field names AI is allowed to update
            allowed_company_fields: Company field names AI is allowed to update
            allowed_line_item_fields: Line item field names AI may create
            transcript: Full transcript text to add as note on the deal
            auto_create_contact_company: Legacy flag; used for both when auto_create_* not provided
            auto_create_companies: If True, create/upsert company (from crm_configurations)
            auto_create_contacts: If True, create/upsert contact (from crm_configurations)
            default_pipeline_id: User-configured pipeline (CRM Configuration screen),
                applied only when creating a brand new deal.
            default_stage_id: User-configured default stage, applied only when creating
                a brand new deal and the transcript didn't resolve an explicit stage.
            create_note: If True and transcript present, create HubSpot note on the deal
            call_outcome: Optional "converted" | "on_hold" | "lost" marked by the rep on
                the confirmation screen. None (default) means unchanged legacy behavior -
                this is optional, not a forced choice on every memo. See
                backend/app/services/hubspot/call_outcome.py for what each value writes.
            lost_reason: Required by ApproveMemoRequest validation when call_outcome is
                "lost" (enforced before this method is ever called); ignored otherwise.
            lost_reason_deal_property: Confirmed override for the deal property that
                stores the portal's closed-lost reason (crm_configurations). When None,
                call_outcome.resolve_lost_reason_property auto-detects one from the
                portal's live deal schema on every sync - not only from the configuration
                screen, so the reason isn't lost just because nobody configured it.
            lost_lead_status_value: This account's own hs_lead_status value that means
                "Lost" (crm_configurations.lost_lead_status_value) - revalidated against
                the live schema before writing (see call_outcome.py). None means not
                configured; the extension wouldn't have offered the Lost button in that
                case, but this method itself just skips the hs_lead_status write and
                relies on the reason note instead (see call_outcome.py module docstring).
            on_hold_lead_status_value: Same as above, for "On Hold".
        Returns:
            SyncResult with success status and created/updated object IDs
        """
        create_companies = auto_create_companies if auto_create_companies is not None else auto_create_contact_company
        create_contacts = auto_create_contacts if auto_create_contacts is not None else auto_create_contact_company
        # When updating existing deal, never create company/contact — deal already has them
        if deal_id and not is_new_deal:
            create_companies = False
            create_contacts = False
        # Contact-first: resolved contact/company IDs are authoritative — never create duplicates
        if contact_id:
            create_contacts = False
        if company_id:
            create_companies = False
        if skip_deal:
            is_new_deal = False
            deal_id = None
            # deal_id=None here is load-bearing beyond this block: Step 6's
            # task merge guard (`if deal_id and not is_new_deal and
            # existing_tasks:`) relies on deal_id being falsy to keep the
            # no-deal flow OUT of merge_tasks (UPDATE/DELETE of existing
            # tasks) even though it now populates existing_tasks from
            # list_tasks_for_contact for dedupe. If deal_id ever stops being
            # forced to None here, that guard silently starts letting the
            # no-deal flow into merge - see the comment there before
            # changing either side of this.
        result = SyncResult(memo_id=str(memo_id))
        t0 = time.perf_counter()
        logger.info(
            "🔗 HubSpot sync started",
            extra=log_domain(
                DOMAIN_HUBSPOT,
                "sync_started",
                memo_id=str(memo_id),
                user_id=user_id,
                deal_id=deal_id,
                is_new_deal=is_new_deal,
                contact_id=contact_id,
                skip_deal=skip_deal,
            ),
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
        if allowed_contact_fields is None:
            allowed_contact_fields = ["firstname", "lastname", "email", "phone", "jobtitle"]
        if allowed_company_fields is None:
            allowed_company_fields = ["name", "domain"]
        if allowed_line_item_fields is None:
            allowed_line_item_fields = ["name", "quantity", "price"]
        
        # Check for existing company/contact IDs from previous failed attempts
        # This prevents creating duplicates on retry
        existing_company_id = None
        existing_contact_id = None
        previous_updates: list[dict[str, Any]] = []
        
        if self.supabase:
            try:
                # Get previous CRM updates for this memo
                previous_updates = await self.crm_updates.get_memo_updates(str(memo_id))
                
                # Find company/contact from prior sync attempts (status may still be pending)
                for update in previous_updates:
                    data = update.get("data", {}) or {}
                    if update.get("action_type") == "upsert_company" and data.get("company_id"):
                        existing_company_id = data["company_id"]
                    elif update.get("action_type") == "upsert_contact" and data.get("contact_id"):
                        existing_contact_id = data["contact_id"]
            except Exception:
                # If we can't check, proceed normally (not critical)
                pass
        
        company_id = company_id or existing_company_id
        contact_id = contact_id or existing_contact_id
        resolved_contact_id = contact_id  # preserve contact-first anchor through upsert logic
        
        try:
            # Step 1: Company — prefer resolved company_id (contact-first), else create/upsert
            if company_id:
                result.company_id = company_id
                try:
                    company_props = company_properties_from_extraction(
                        extraction,
                        allowed_fields=allowed_company_fields,
                        identity_props=self.companies.map_extraction_to_properties(extraction),
                    )
                    company_props.pop("name", None)
                    company_props = drop_call_unsafe_props(
                        company_props,
                        existing_record=True,
                        current={},
                        object_type="companies",
                    )
                    if company_props:
                        async with self.crm_updates.track(
                            memo_id=str(memo_id),
                            user_id=user_id,
                            crm_connection_id=str(connection_id),
                            action_type="upsert_company",
                            resource_type="company",
                        ) as tracked:
                            await self.companies.update(company_id, company_props)
                            tracked.data = {"company_id": company_id, "updated_fields": list(company_props.keys())}
                            tracked.resource_id = company_id
                            logger.info(
                                "✅ Company properties updated (contact-first)",
                                extra=log_domain(
                                    DOMAIN_HUBSPOT,
                                    "company_props_updated",
                                    company_id=company_id,
                                    memo_id=str(memo_id),
                                    fields=list(company_props.keys()),
                                ),
                            )
                except Exception as e:
                    logger.warning(
                        "⚠️ Contact-first company update failed: %s",
                        e,
                        extra=log_domain(DOMAIN_HUBSPOT, "company_anchor_update_failed", memo_id=str(memo_id)),
                    )
            elif create_companies and extraction.companyName:
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
                        async with self.crm_updates.track(
                            memo_id=str(memo_id),
                            user_id=user_id,
                            crm_connection_id=str(connection_id),
                            action_type="upsert_company",
                            resource_type="company",
                        ) as tracked:
                            company = await self.companies.create_or_update(
                                extraction, allowed_fields=allowed_company_fields
                            )
                            if company:
                                company_id = company.id
                                result.company_id = company_id
                                tracked.data = {"company_id": company_id, "name": extraction.companyName}
                                tracked.resource_id = company_id
                                logger.info(
                                    "✅ Company upserted",
                                    extra=log_domain(DOMAIN_HUBSPOT, "company_upserted", company_id=company_id, company_name=extraction.companyName),
                                )
                except Exception as e:
                    inc_pipeline_error(DOMAIN_HUBSPOT, "company_upsert")
                    logger.warning(
                        "⚠️ Company upsert failed",
                        extra=log_domain(DOMAIN_HUBSPOT, "company_failed", memo_id=str(memo_id), error=str(e)),
                    )
            
            # Step 2: Contact (only when user setting allows)
            # Pull from extraction or raw_extraction (LLM may put in either)
            raw = extraction.raw_extraction or {}
            company = extraction.companyName or _clean_extracted_name(raw.get("companyName")) or _clean_extracted_name(raw.get("company_name"))
            contact_name = extraction.contactName or _clean_extracted_name(raw.get("contactName")) or _clean_extracted_name(raw.get("contact_name"))
            from app.services.hubspot.contact_identity import real_contact_email_or_none

            contact_email = real_contact_email_or_none(
                extraction.contactEmail or raw.get("contactEmail") or raw.get("contact_email")
            )
            # Fallback: when we only have company, create "Contact at {company}"
            if company and not contact_name and not contact_email:
                contact_name = f"Contact at {company}"
            extraction_for_contact = extraction.model_copy(
                update={
                    "companyName": company or extraction.companyName,
                    "contactName": contact_name or extraction.contactName,
                    "contactEmail": contact_email,
                }
            )
            # Contact-first: update the resolved contact by ID (not deal's primary contact)
            if resolved_contact_id:
                try:
                    async with self.crm_updates.track(
                        memo_id=str(memo_id),
                        user_id=user_id,
                        crm_connection_id=str(connection_id),
                        action_type="upsert_contact",
                        resource_type="contact",
                    ) as tracked:
                        props = _contact_props_updating_existing(
                            self.contacts, extraction_for_contact, allowed_contact_fields
                        )
                        props.pop("email", None)  # never rotate the locked identity email
                        if props:
                            await self.contacts.update(resolved_contact_id, props)
                        contact_id = resolved_contact_id
                        result.contact_id = contact_id
                        tracked.data = {"contact_id": contact_id, "email": extraction_for_contact.contactEmail}
                        tracked.resource_id = contact_id
                        logger.info(
                            "✅ Contact updated (contact-first)",
                            extra=log_domain(
                                DOMAIN_HUBSPOT,
                                "contact_anchor_updated",
                                contact_id=contact_id,
                                memo_id=str(memo_id),
                                fields=list(props.keys()),
                            ),
                        )
                except Exception as e:
                    logger.warning(
                        "⚠️ Contact-first update failed: %s",
                        e,
                        extra=log_domain(DOMAIN_HUBSPOT, "contact_anchor_failed", memo_id=str(memo_id)),
                    )
            else:
                should_create_contact = create_contacts and (
                    extraction_for_contact.contactEmail
                    or extraction_for_contact.contactName
                    or extraction_for_contact.contactPhone
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
                                    props = _contact_props_updating_existing(
                                        self.contacts, extraction_for_contact, allowed_contact_fields
                                    )
                                    if props:
                                        async with self.crm_updates.track(
                                            memo_id=str(memo_id),
                                            user_id=user_id,
                                            crm_connection_id=str(connection_id),
                                            action_type="upsert_contact",
                                            resource_type="contact",
                                        ) as tracked:
                                            await self.contacts.update(primary_contact_id, props)
                                            contact_id = primary_contact_id
                                            result.contact_id = contact_id
                                            tracked.data = {"contact_id": primary_contact_id, "email": extraction_for_contact.contactEmail}
                                            tracked.resource_id = primary_contact_id
                                            logger.info(
                                                "✅ Contact updated (deal association)",
                                                extra=log_domain(DOMAIN_HUBSPOT, "contact_updated", contact_id=primary_contact_id, memo_id=str(memo_id)),
                                            )
                            except Exception as e:
                                # NOT re-raised: this is the "try updating the deal's
                                # existing contact" step specifically. Its own HubSpot
                                # write (if props was non-empty) is tracked above and
                                # already has its 'failed' row - this local except only
                                # decides whether to fall through to the create fallback
                                # below, it doesn't need its own row.
                                logger.warning(
                                    "⚠️ Failed to update deal contact, will create: %s",
                                    e,
                                    extra=log_domain(DOMAIN_HUBSPOT, "contact_update_fallback", memo_id=str(memo_id)),
                                )
                            if not contact_id:
                                async with self.crm_updates.track(
                                    memo_id=str(memo_id),
                                    user_id=user_id,
                                    crm_connection_id=str(connection_id),
                                    action_type="upsert_contact",
                                    resource_type="contact",
                                ) as tracked:
                                    contact = await self.contacts.create_or_update(
                                        extraction_for_contact, allowed_fields=allowed_contact_fields
                                    )
                                    if contact:
                                        contact_id = contact.id
                                        result.contact_id = contact_id
                                        tracked.data = {"contact_id": contact_id, "email": extraction_for_contact.contactEmail}
                                        tracked.resource_id = contact_id
                                        logger.info(
                                            "✅ Contact upserted (fallback)",
                                            extra=log_domain(DOMAIN_HUBSPOT, "contact_upserted", contact_id=contact_id, memo_id=str(memo_id)),
                                        )
                        else:
                            async with self.crm_updates.track(
                                memo_id=str(memo_id),
                                user_id=user_id,
                                crm_connection_id=str(connection_id),
                                action_type="upsert_contact",
                                resource_type="contact",
                            ) as tracked:
                                contact = await self.contacts.create_or_update(
                                    extraction_for_contact, allowed_fields=allowed_contact_fields
                                )
                                if contact:
                                    contact_id = contact.id
                                    result.contact_id = contact_id
                                    tracked.data = {"contact_id": contact_id, "email": extraction_for_contact.contactEmail}
                                    tracked.resource_id = contact_id
                                    logger.info(
                                        "✅ Contact upserted",
                                        extra=log_domain(DOMAIN_HUBSPOT, "contact_upserted", contact_id=contact_id, memo_id=str(memo_id), company=extraction_for_contact.companyName, contact_name=extraction_for_contact.contactName),
                                    )
                    except Exception as e:
                        inc_pipeline_error(DOMAIN_HUBSPOT, "contact_upsert")
                        logger.warning(
                            "⚠️ Contact upsert failed",
                            extra=log_domain(DOMAIN_HUBSPOT, "contact_failed", memo_id=str(memo_id), error=str(e), company=extraction_for_contact.companyName, contact=extraction_for_contact.contactName),
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
            
            # Step 4: Deal - Create or Update (skipped in contact-only mode)
            if not skip_deal:
                try:
                    if deal_id and not is_new_deal:
                        # UPDATE MODE: Merge existing deal with new extraction
                        # 1. Fetch current deal properties
                        fetch_props = list(set(
                            allowed_fields + [
                                "dealname", "amount", "closedate", "description", "dealstage", "pipeline"
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
                            allowed_fields=allowed_fields,
                            # Scope stage resolution to the deal's own current pipeline, so an
                            # inferred stage label never gets paired with the wrong pipeline
                            # (HubSpot rejects that combination). This does NOT force-move the
                            # deal to a different pipeline - default_pipeline_id here is only
                            # used to scope which pipeline's stages we search.
                            default_pipeline_id=existing_props.get("pipeline"),
                            is_new_deal=False,
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
                            async with self.crm_updates.track(
                                memo_id=str(memo_id),
                                user_id=user_id,
                                crm_connection_id=str(connection_id),
                                action_type="update_deal",
                                resource_type="deal",
                            ) as tracked:
                                deal = await self.deals.update(
                                    deal_id,
                                    filtered_properties,
                                    hubspot_owner_id=hubspot_owner_id,
                                )
                                result.deal_id = deal.id
                                tracked.data = {
                                    "deal_id": deal.id,
                                    "updated_fields": list(filtered_properties.keys()),
                                }
                                tracked.resource_id = deal.id
                                logger.info(
                                    "✅ Deal updated",
                                    extra=log_domain(DOMAIN_HUBSPOT, "deal_updated", deal_id=deal.id, memo_id=str(memo_id), updated_fields=list(filtered_properties.keys())),
                                )
                        result.deal_name = existing_props.get("dealname") or "Deal"
                    else:
                        # CREATE MODE: Create new deal
                        async with self.crm_updates.track(
                            memo_id=str(memo_id),
                            user_id=user_id,
                            crm_connection_id=str(connection_id),
                            action_type="create_deal",
                            resource_type="deal",
                        ) as tracked:
                            deal = await self.deals.create_or_update(
                                extraction,
                                contact_id=contact_id,
                                company_id=company_id,
                                hubspot_owner_id=hubspot_owner_id,
                                allowed_fields=allowed_fields,
                                default_pipeline_id=default_pipeline_id,
                                default_stage_id=default_stage_id,
                            )
                            result.deal_id = deal.id
                            tracked.data = {
                                "deal_id": deal.id,
                                "amount": extraction.dealAmount,
                                "stage": extraction.dealStage,
                            }
                            tracked.resource_id = deal.id
                            logger.info(
                                "✅ Deal created",
                                extra=log_domain(DOMAIN_HUBSPOT, "deal_created", deal_id=deal.id, memo_id=str(memo_id), amount=extraction.dealAmount, stage=extraction.dealStage),
                            )
                        result.deal_name = (deal.properties or {}).get("dealname") or extraction.companyName or "Deal"

                    deal_id = result.deal_id

                except Exception as e:
                    # track() above already wrote the 'failed' row (if a HubSpot
                    # call was attempted at all - e.g. this also catches
                    # exceptions raised before either track() block, like
                    # merge_svc.merge_properties itself failing).
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
                    return result

                # Step 4b: UPDATE MODE — update the deal's primary contact by ID when
                # we still have name/role/phone (or nested props) and no locked contact.
                if deal_id and not is_new_deal and (extraction_for_contact.contactName or extraction_for_contact.contactRole or extraction_for_contact.contactPhone or (extraction.raw_extraction or {}).get("contact_properties")):
                    if not contact_id:
                        try:
                            contact_ids = await self.associations.get_associations("deals", deal_id, "contacts")
                            if contact_ids:
                                primary_contact_id = contact_ids[0]
                                props = _contact_props_updating_existing(
                                    self.contacts, extraction_for_contact, allowed_contact_fields
                                )
                                props.pop("email", None)
                                if props:
                                    async with self.crm_updates.track(
                                        memo_id=str(memo_id),
                                        user_id=user_id,
                                        crm_connection_id=str(connection_id),
                                        action_type="upsert_contact",
                                        resource_type="contact",
                                    ) as tracked:
                                        await self.contacts.update(primary_contact_id, props)
                                        contact_id = primary_contact_id
                                        result.contact_id = primary_contact_id
                                        tracked.data = {"contact_id": primary_contact_id, "updated_fields": list(props.keys())}
                                        tracked.resource_id = primary_contact_id
                                        logger.info(
                                            "✅ Contact updated (deal association)",
                                            extra=log_domain(DOMAIN_HUBSPOT, "contact_updated", contact_id=primary_contact_id, memo_id=str(memo_id)),
                                        )
                        except Exception as e:
                            logger.warning(
                                "⚠️ Failed to update associated contact: %s",
                                e,
                                extra=log_domain(DOMAIN_HUBSPOT, "contact_assoc_update_failed", memo_id=str(memo_id)),
                            )

                # Step 4c: UPDATE MODE - Patch associated company with allowlisted company_properties
                if deal_id and not is_new_deal and allowed_company_fields:
                    company_props = company_properties_from_extraction(
                        extraction,
                        allowed_fields=allowed_company_fields,
                        identity_props=self.companies.map_extraction_to_properties(extraction),
                    )
                    company_props.pop("name", None)  # don't rename company from memo by default
                    company_props = drop_call_unsafe_props(
                        company_props,
                        existing_record=True,
                        current={},
                        object_type="companies",
                    )
                    if company_props:
                        try:
                            cids = await self.associations.get_associations("deals", deal_id, "companies")
                            if cids:
                                async with self.crm_updates.track(
                                    memo_id=str(memo_id),
                                    user_id=user_id,
                                    crm_connection_id=str(connection_id),
                                    action_type="upsert_company",
                                    resource_type="company",
                                ) as tracked:
                                    await self.companies.update(cids[0], company_props)
                                    company_id = company_id or cids[0]
                                    result.company_id = company_id
                                    tracked.data = {
                                        "company_id": cids[0],
                                        "updated_fields": list(company_props.keys()),
                                    }
                                    tracked.resource_id = cids[0]
                                    logger.info(
                                        "✅ Company properties updated",
                                        extra=log_domain(
                                            DOMAIN_HUBSPOT,
                                            "company_props_updated",
                                            company_id=cids[0],
                                            memo_id=str(memo_id),
                                            fields=list(company_props.keys()),
                                        ),
                                    )
                        except Exception as e:
                            logger.warning(
                                "⚠️ Failed to update associated company: %s",
                                e,
                                extra=log_domain(DOMAIN_HUBSPOT, "company_assoc_update_failed", memo_id=str(memo_id)),
                            )

                # Step 4d: Create line items on the deal when allowlisted and extracted
                line_items = line_items_from_extraction(
                    extraction, allowed_fields=allowed_line_item_fields
                )
                if deal_id and line_items:
                    for item_props in line_items:
                        try:
                            async with self.crm_updates.track(
                                memo_id=str(memo_id),
                                user_id=user_id,
                                crm_connection_id=str(connection_id),
                                action_type="create_line_item",
                                resource_type="line_item",
                            ) as tracked:
                                # Prefer parent deal property (commerce) + default association
                                create_body: dict[str, Any] = {
                                    "properties": {
                                        **item_props,
                                        "hs_parent_deal_id": str(deal_id),
                                    }
                                }
                                created = await self.client.post(
                                    "/crm/v3/objects/line_items",
                                    data=create_body,
                                )
                                line_item_id = (created or {}).get("id")
                                if line_item_id:
                                    try:
                                        await self.client.put(
                                            f"/crm/v4/objects/line_item/{line_item_id}/associations/default/deal/{deal_id}",
                                            data=None,
                                        )
                                    except Exception:
                                        pass
                                    tracked.data = {
                                        "line_item_id": line_item_id,
                                        "deal_id": deal_id,
                                        "properties": item_props,
                                    }
                                    tracked.resource_id = line_item_id
                                    logger.info(
                                        "✅ Line item created",
                                        extra=log_domain(
                                            DOMAIN_HUBSPOT,
                                            "line_item_created",
                                            line_item_id=line_item_id,
                                            deal_id=deal_id,
                                            memo_id=str(memo_id),
                                        ),
                                    )
                        except Exception as e:
                            # Missing scopes or portal commerce setup should not fail the whole sync
                            logger.warning(
                                "⚠️ Line item create failed: %s",
                                e,
                                extra=log_domain(DOMAIN_HUBSPOT, "line_item_failed", memo_id=str(memo_id)),
                            )

                # Step 5: Associate deal → contact, deal → company (always when we have them)            # Applies to both new deals and existing deals being updated
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

            # Step 6: Tasks - merge with existing when updating a deal, else create new.
            # Associate to every object we have (deal + contact + company), same as notes.
            company_id = await self._resolve_company_id(company_id, contact_id, deal_id)
            if company_id:
                result.company_id = company_id
            tasks_target_id = deal_id or contact_id or company_id
            tasks_target_type = "deal" if deal_id else ("contact" if contact_id else None)
            if tasks_target_id:
                logger.info(
                    "🎯 Task association target resolved",
                        extra=log_domain(
                            DOMAIN_HUBSPOT, "task_target_resolved",
                            memo_id=str(memo_id), target_type=tasks_target_type,
                            deal_id=deal_id, contact_id=contact_id, company_id=company_id,
                        ),
                )
            tasks_already_synced = CRMUpdatesService.is_action_already_done(
                previous_updates, ("create_tasks", "merge_tasks")
            )
            tasks_requested_count = len(extraction.nextSteps or [])
            task_batch = TaskBatchResult()
            tasks_merge_mode = False
            tasks_merge_failed = False

            if not tasks_target_id and tasks_requested_count:
                logger.warning(
                    "Cannot create tasks — no deal or contact target",
                    extra=log_domain(
                        DOMAIN_HUBSPOT, "tasks_no_target",
                        memo_id=str(memo_id), requested_count=tasks_requested_count,
                    ),
                )
                result.tasks_requested_count = tasks_requested_count
                result.tasks_created_count = 0
                result.tasks_warning = summarize_task_batch(
                    tasks_requested_count,
                    task_batch,
                    no_target=True,
                )
            elif tasks_target_id and extraction.nextSteps and tasks_already_synced:
                logger.info(
                    "Skipping duplicate task sync for memo retry",
                    extra=log_domain(
                        DOMAIN_HUBSPOT, "tasks_skipped_duplicate",
                        deal_id=deal_id, contact_id=contact_id, memo_id=str(memo_id),
                        requested_count=tasks_requested_count,
                    ),
                )
                result.tasks_requested_count = tasks_requested_count
                result.tasks_created_count = 0
                result.tasks_warning = summarize_task_batch(
                    tasks_requested_count,
                    task_batch,
                    already_synced=True,
                )
            elif tasks_target_id and extraction.nextSteps and not tasks_already_synced:
                try:
                    used_merge = False
                    if deal_id and not is_new_deal:
                        existing_tasks = await self.tasks.list_tasks_for_deal(deal_id)
                    elif contact_id and not deal_id:
                        # No-deal flow (contact-first / skip_deal): dedupe
                        # against the contact's own existing tasks instead
                        # of treating this as a blank slate. Without this,
                        # existing_subjects was always empty here, so a
                        # retried memo with no deal could recreate the same
                        # next-step tasks on the contact every time - the
                        # deal flow above never had this hole because it
                        # always looked existing_tasks up first.
                        existing_tasks = await self.tasks.list_tasks_for_contact(contact_id)
                    else:
                        existing_tasks = []
                    existing_subjects = {
                        _normalize_task_subject(t.get("subject", "")) for t in existing_tasks
                    }
                    # `deal_id and` here is NOT redundant with `existing_tasks`
                    # being truthy - it's the only thing keeping the no-deal
                    # (contact-first / skip_deal) flow out of merge_tasks.
                    # That flow populates existing_tasks too (from
                    # list_tasks_for_contact, above) so it can dedupe by
                    # subject on create, but it must NEVER reach merge:
                    # merge_tasks does UPDATE and DELETE against existing
                    # tasks, not just comparison, and a contact's tasks may
                    # have been created by someone/something else entirely -
                    # not just our own prior syncs. skip_deal forces
                    # deal_id=None (see that block) specifically so this
                    # condition short-circuits to False for that flow
                    # regardless of existing_tasks. Do not drop `deal_id and`
                    # to "simplify" this - that would silently turn "dedupe
                    # only" into "merge can delete a contact's tasks".
                    if deal_id and not is_new_deal and existing_tasks:
                        # UPDATE MODE: Fetch existing tasks, merge with new extraction
                        tasks_merge_mode = True
                        merge_svc = TaskMergeService()
                        merge_result = await merge_svc.merge_tasks(
                            existing_tasks=existing_tasks,
                            extraction=extraction,
                            transcript=transcript,
                        )
                        if merge_result.merge_failed:
                            tasks_merge_failed = True
                            logger.warning(
                                "Task merge failed — falling back to create-from-extraction",
                                extra=log_domain(
                                    DOMAIN_HUBSPOT, "tasks_merge_failed",
                                    memo_id=str(memo_id), deal_id=deal_id,
                                    requested_count=tasks_requested_count,
                                    existing_task_count=len(existing_tasks),
                                ),
                            )
                        else:
                            created_ids = []
                            merge_skipped_duplicates = 0
                            # Execute add
                            for add_op in merge_result.add:
                                schedule_hints = _next_step_schedule_hints(extraction)
                                hint = schedule_hints[len(created_ids)] if len(created_ids) < len(schedule_hints) else None
                                formatted = format_next_step_task(
                                    add_op.subject,
                                    contact_name=extraction.contactName,
                                    schedule_hint=hint or add_op.subject,
                                )
                                norm = _normalize_task_subject(formatted.subject)
                                if norm in existing_subjects:
                                    merge_skipped_duplicates += 1
                                    logger.info(
                                        "Merge add skipped as duplicate subject",
                                        extra=log_domain(
                                            DOMAIN_HUBSPOT, "tasks_merge_add_skipped_duplicate",
                                            subject=formatted.subject[:80], deal_id=deal_id,
                                        ),
                                    )
                                    continue
                                due = add_op.due_date or formatted.due_date
                                tid = await self.tasks.create_task(
                                    subject=formatted.subject,
                                    due_date=due,
                                    deal_id=deal_id,
                                    contact_id=contact_id,
                                    company_id=company_id,
                                    body=build_task_body(
                                        step=add_op.subject,
                                        summary=extraction.summary,
                                        formatted_subject=formatted.subject,
                                    ),
                                    hubspot_owner_id=hubspot_owner_id,
                                    task_type=formatted.task_type,
                                )
                                if tid:
                                    created_ids.append(tid)
                                    existing_subjects.add(norm)
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
                            task_batch.created_ids.extend(created_ids)
                            logger.info(
                                "Task merge completed",
                                extra=log_domain(
                                    DOMAIN_HUBSPOT, "tasks_merge_complete",
                                    memo_id=str(memo_id), deal_id=deal_id,
                                    add_requested=len(merge_result.add),
                                    created_count=len(created_ids),
                                    updated_count=len(merge_result.update),
                                    deleted_count=len(merge_result.delete),
                                    duplicate_skips=merge_skipped_duplicates,
                                ),
                            )
                            if (
                                not created_ids
                                and not merge_result.update
                                and not merge_result.delete
                                and tasks_requested_count
                            ):
                                logger.info(
                                    "Task merge decided no changes",
                                    extra=log_domain(
                                        DOMAIN_HUBSPOT, "tasks_merge_no_changes",
                                        memo_id=str(memo_id), deal_id=deal_id,
                                        requested_count=tasks_requested_count,
                                        existing_task_count=len(existing_tasks),
                                    ),
                                )
                            if created_ids or merge_result.update or merge_result.delete:
                                # DEBT, on purpose: NOT migrated to track(). track()'s
                                # reserve->execute->confirm models ONE HubSpot write; this
                                # step is a batch of independent sub-operations (N creates,
                                # M updates, K deletes) executed in three separate loops
                                # above, any subset of which can succeed while others fail.
                                # A single crm_updates row can't represent partial success
                                # at that granularity without inventing a new data shape.
                                # Kept on the pre-track() write-after-success pattern, with
                                # the ERROR-level audit_e logging below as the mitigation
                                # until this gets real per-operation tracking.
                                try:
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
                                except Exception as audit_e:
                                    # HubSpot already applied the merge - only the audit
                                    # write failed. Distinct from the generic "tasks_failed"
                                    # below (that means HubSpot itself failed): this means
                                    # crm_updates has no record of it, so a retry of this
                                    # memo won't see tasks_already_synced and may re-merge
                                    # the same tasks. Logged at ERROR (not swallowed as a
                                    # warning) so it's monitorable until the write-order fix
                                    # (pending row before the HubSpot call) lands.
                                    inc_pipeline_error(DOMAIN_HUBSPOT, "tasks_audit_write_failed")
                                    logger.error(
                                        "🚨 Tasks merged in HubSpot but crm_updates write failed - retry may re-merge",
                                        extra=log_domain(
                                            DOMAIN_HUBSPOT, "tasks_created_but_audit_write_failed",
                                            memo_id=str(memo_id), deal_id=deal_id, contact_id=contact_id,
                                            created_ids=created_ids,
                                            updated=[u.id for u in merge_result.update],
                                            deleted=merge_result.delete,
                                            error=str(audit_e),
                                        ),
                                    )
                            used_merge = True
                    if not used_merge:
                        # CREATE MODE, no existing tasks, or no deal at all: create from
                        # extraction. Associates to deal, contact, and company when present.
                        async with self.crm_updates.track(
                            memo_id=str(memo_id),
                            user_id=user_id,
                            crm_connection_id=str(connection_id),
                            action_type="create_tasks",
                            resource_type="task",
                        ) as tracked:
                            batch = await self.tasks.create_tasks_from_extraction(
                                extraction,
                                deal_id=deal_id,
                                contact_id=contact_id,
                                company_id=company_id,
                                hubspot_owner_id=hubspot_owner_id,
                                existing_subjects=existing_subjects,
                            )
                            task_batch = batch
                            if batch.created_ids:
                                tracked.data = {
                                    "task_ids": batch.created_ids,
                                    "count": batch.created_count,
                                    "skipped": len(batch.skipped),
                                }
                                logger.info(
                                    "✅ Tasks created",
                                    extra=log_domain(
                                        DOMAIN_HUBSPOT, "tasks_created",
                                        target_type=tasks_target_type, deal_id=deal_id, contact_id=contact_id,
                                        count=batch.created_count,
                                        task_ids=batch.created_ids,
                                        skipped_count=len(batch.skipped),
                                    ),
                                )
                            elif tasks_requested_count:
                                tracked.data = {
                                    "task_ids": [],
                                    "count": 0,
                                    "skipped": len(batch.skipped),
                                    "skip_reasons": [s.reason for s in batch.skipped],
                                }
                                logger.warning(
                                    "No tasks created from nextSteps",
                                    extra=log_domain(
                                        DOMAIN_HUBSPOT, "tasks_none_created",
                                        target_type=tasks_target_type, deal_id=deal_id, contact_id=contact_id,
                                        requested_count=tasks_requested_count,
                                        skipped_count=len(batch.skipped),
                                        skip_reasons=[s.reason for s in batch.skipped],
                                    ),
                                )
                except Exception as e:
                    inc_pipeline_error(DOMAIN_HUBSPOT, "create_tasks")
                    logger.warning(
                        "Failed to create tasks for %s %s: %s",
                        "deal" if deal_id else "contact", tasks_target_id, e,
                        extra=log_domain(
                            DOMAIN_HUBSPOT, "tasks_failed",
                            deal_id=deal_id, contact_id=contact_id, error=str(e),
                            requested_count=tasks_requested_count,
                        ),
                    )

                result.tasks_requested_count = tasks_requested_count
                result.tasks_created_count = task_batch.created_count
                result.tasks_warning = summarize_task_batch(
                    tasks_requested_count,
                    task_batch,
                    merge_mode=tasks_merge_mode and not tasks_merge_failed,
                    merge_failed=tasks_merge_failed,
                )

            # Step 7: Create one formatted note per memo, associated to every object
            # that exists (deal, contact, company) in a single call. Runs whether or
            # not skip_deal is set - the transcript must not be lost when there's no
            # deal. A failed individual association is logged and skipped, never
            # escalated: the note (and the associations that did work) still land.
            #
            # When call_outcome == 'lost', the Lost reason is merged into THIS note
            # (see format_hubspot_note_body) rather than creating a second one - see
            # call_outcome.py module docstring for why. outcome_note_merged_this_run
            # (and outcome_note_already_recorded, computed below from previous_updates
            # for retries) tell Step 8 whether it still needs its own standalone note.
            outcome_note_merged_this_run = False
            if create_note and transcript and transcript.strip() and (deal_id or contact_id or company_id):
                # Dedupe by memo, not by deal: one memo produces at most one note,
                # regardless of how many objects it ends up associated with.
                note_already_created = CRMUpdatesService.is_action_already_done(
                    previous_updates, ("create_note",)
                )
                if note_already_created:
                    logger.info(
                        "Skipping duplicate transcript note",
                        extra=log_domain(DOMAIN_HUBSPOT, "note_skipped_duplicate", memo_id=str(memo_id)),
                    )
                else:
                    try:
                        async with self.crm_updates.track(
                            memo_id=str(memo_id),
                            user_id=user_id,
                            crm_connection_id=str(connection_id),
                            action_type="create_note",
                            resource_type="note",
                        ) as tracked:
                            from .note_format import format_hubspot_note_body

                            note_body = format_hubspot_note_body(
                                summary=getattr(extraction, "summary", None),
                                transcript=transcript,
                                source="hubspot_call",
                                call_outcome=call_outcome,
                                lost_reason=lost_reason,
                            )
                            note_properties = {
                                "hs_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "hs_note_body": note_body,
                            }
                            if hubspot_owner_id:
                                note_properties["hubspot_owner_id"] = hubspot_owner_id

                            # (object_type, object_id, associationTypeId) for every object we have
                            note_targets: list[tuple[str, str, int]] = []
                            if deal_id:
                                note_targets.append(("deals", str(deal_id), self.associations.NOTE_TO_DEAL))
                            if contact_id:
                                note_targets.append(("contacts", str(contact_id), self.associations.NOTE_TO_CONTACT))
                            if company_id:
                                note_targets.append(("companies", str(company_id), self.associations.NOTE_TO_COMPANY))

                            logger.info(
                                "🎯 Note association targets resolved",
                                extra=log_domain(
                                    DOMAIN_HUBSPOT, "note_targets_resolved",
                                    memo_id=str(memo_id),
                                    targets=[f"{t}:{oid}" for t, oid, _ in note_targets],
                                ),
                            )

                            note_id = None
                            try:
                                # Happy path: one call, all associations in the array. HubSpot
                                # validates the whole create atomically, so if this succeeds,
                                # every association below was created too.
                                created = await self.client.post(
                                    "/crm/v3/objects/notes",
                                    data={
                                        "properties": note_properties,
                                        "associations": [
                                            {
                                                "to": {"id": to_id},
                                                "types": [
                                                    {
                                                        "associationCategory": "HUBSPOT_DEFINED",
                                                        "associationTypeId": type_id,
                                                    }
                                                ],
                                            }
                                            for _, to_id, type_id in note_targets
                                        ],
                                    },
                                )
                                note_id = (created or {}).get("id")
                                if note_id:
                                    for object_type, to_id, type_id in note_targets:
                                        logger.info(
                                            "✅ Note associated",
                                            extra=log_domain(
                                                DOMAIN_HUBSPOT, "note_associated",
                                                note_id=note_id, object_type=object_type,
                                                object_id=to_id, association_type_id=type_id,
                                                memo_id=str(memo_id),
                                            ),
                                        )
                            except (HubSpotScopeError, HubSpotValidationError, HubSpotNotFoundError) as e:
                                # Only retry when HubSpot rejected the request BEFORE creating
                                # anything: 403 (missing scope), 400 (e.g. bad associationTypeId)
                                # and 404 (bad target id) are all pre-creation validation
                                # failures per HubSpot's API - the note above was never
                                # persisted, so retrying bare cannot produce a duplicate.
                                # Any other exception (timeout, 5xx, network error) is
                                # ambiguous about server-side state and is deliberately NOT
                                # retried here - it propagates out of this async-with, which
                                # marks the row 'failed' and re-raises to the outer except
                                # below, which logs and gives up. We'd rather lose this note
                                # once than risk leaving two on the customer's timeline.
                                logger.warning(
                                    "⚠️ Note create with associations failed (safe to retry bare): %s",
                                    e,
                                    extra=log_domain(DOMAIN_HUBSPOT, "note_create_with_assoc_failed", memo_id=str(memo_id)),
                                )
                                created = await self.client.post(
                                    "/crm/v3/objects/notes",
                                    data={"properties": note_properties},
                                )
                                note_id = (created or {}).get("id")
                                if note_id:
                                    for object_type, to_id, type_id in note_targets:
                                        try:
                                            await self.associations.create_association(
                                                "notes", note_id, object_type, to_id,
                                            )
                                            logger.info(
                                                "✅ Note associated (fallback)",
                                                extra=log_domain(
                                                    DOMAIN_HUBSPOT, "note_associated",
                                                    note_id=note_id, object_type=object_type,
                                                    object_id=to_id, association_type_id=type_id,
                                                    memo_id=str(memo_id),
                                                ),
                                            )
                                        except Exception as assoc_e:
                                            logger.warning(
                                                "⚠️ Failed to associate note %s to %s %s: %s",
                                                note_id, object_type, to_id, assoc_e,
                                                extra=log_domain(
                                                    DOMAIN_HUBSPOT, "note_association_failed",
                                                    note_id=note_id, object_type=object_type,
                                                    object_id=to_id, memo_id=str(memo_id),
                                                ),
                                            )

                            if note_id:
                                outcome_note_merged_this_run = call_outcome == "lost"
                                tracked.data = {
                                    "note_id": note_id,
                                    "deal_id": deal_id,
                                    "contact_id": contact_id,
                                    "company_id": company_id,
                                    # Read back on retries (see previous_updates scan
                                    # below) so a second approve attempt doesn't create
                                    # a redundant standalone outcome note - the reason
                                    # is already merged into this one.
                                    **({"outcome_note_merged": True} if outcome_note_merged_this_run else {}),
                                }
                                tracked.resource_id = note_id
                                logger.info(
                                    "✅ Note created",
                                    extra=log_domain(DOMAIN_HUBSPOT, "note_created", deal_id=deal_id, contact_id=contact_id, company_id=company_id),
                                )
                    except Exception as e:
                        inc_pipeline_error(DOMAIN_HUBSPOT, "create_note")
                        logger.warning(
                            "Failed to create transcript note (deal=%s contact=%s company=%s): %s. "
                            "Ensure crm.objects.notes.write scope.",
                            deal_id, contact_id, company_id, e,
                            extra=log_domain(DOMAIN_HUBSPOT, "note_failed", memo_id=str(memo_id), error=str(e)),
                        )

            # Step 8: Call outcome (Converted / On Hold / Lost). Optional - only
            # runs when the rep actually marked one on the confirmation screen.
            # Deliberately its own top-level try/except (not just relying on the
            # inner functions' own try/excepts): a bug in call_outcome.py itself
            # (e.g. an unexpected exception building CallOutcomeContext) must
            # degrade the same way as every HubSpot write in this method - log,
            # warn, keep whatever Steps 1-7 already wrote - never turn into a
            # 500 that discards a sync that otherwise fully succeeded.
            if call_outcome:
                try:
                    # A prior run may have already merged the reason into a
                    # successful create_note (see outcome_note_merged_this_run
                    # above) - checked from previous_updates, not just this
                    # run's local flag, so a retry doesn't create a second,
                    # redundant standalone note for the same reason.
                    outcome_note_already_recorded = outcome_note_merged_this_run or any(
                        u.get("action_type") == "create_note"
                        and u.get("status") == "success"
                        and (u.get("data") or {}).get("outcome_note_merged")
                        for u in previous_updates
                    )
                    outcome_ctx = CallOutcomeContext(
                        memo_id=str(memo_id),
                        user_id=user_id,
                        connection_id=str(connection_id),
                        call_outcome=call_outcome,
                        lost_reason=lost_reason,
                        lost_reason_deal_property_configured=lost_reason_deal_property,
                        lost_lead_status_value=lost_lead_status_value,
                        on_hold_lead_status_value=on_hold_lead_status_value,
                        contact_id=contact_id,
                        deal_id=deal_id,
                        company_id=company_id,
                        contact_name=extraction_for_contact.contactName or extraction.contactName,
                        hubspot_owner_id=hubspot_owner_id,
                        outcome_note_already_recorded=outcome_note_already_recorded,
                        previous_updates=previous_updates,
                        extraction=extraction,
                    )
                    outcome_result = await apply_call_outcome(
                        outcome_ctx,
                        crm_updates=self.crm_updates,
                        contacts=self.contacts,
                        deals=self.deals,
                        tasks=self.tasks,
                        client=self.client,
                        associations=self.associations,
                        schema_service=self.deals.schema,
                    )
                    result.outcome_warning = outcome_result.warning
                    result.outcome_failed = outcome_result.failed
                except Exception as e:
                    # Unexpected bug in call_outcome.py itself (not a normal
                    # HubSpot write failure, those are already caught inside
                    # apply_call_outcome) - treat as critical: we genuinely
                    # don't know whether anything was saved.
                    result.outcome_failed = "Couldn't record the call outcome in HubSpot."
                    logger.warning(
                        "⚠️ Call outcome step failed: %s",
                        e,
                        extra=log_domain(DOMAIN_HUBSPOT, "call_outcome_step_failed", memo_id=str(memo_id), error=str(e)),
                    )

            # Success!
            result.success = True
            elapsed = time.perf_counter() - t0
            record_sync_duration(elapsed, "success")
            logger.info(
                "✅ HubSpot sync complete",
                extra=log_domain(
                    DOMAIN_HUBSPOT, "sync_complete",
                    memo_id=str(memo_id), deal_id=result.deal_id, company_id=result.company_id,
                    contact_id=result.contact_id, duration_ms=round(elapsed * 1000, 2),
                    tasks_requested=result.tasks_requested_count,
                    tasks_created=result.tasks_created_count,
                    tasks_warning=bool(result.tasks_warning),
                ),
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
                ui_domain = None
                metadata = {}
                
                # Try connection metadata first
                if self.supabase:
                    conn = self.supabase.table("crm_connections").select("metadata").eq("id", str(connection_id)).single().execute()
                    if conn.data:
                        metadata = conn.data.get("metadata", {}) or {}
                        portal_id = metadata.get("portal_id")
                        region = metadata.get("region", "na1")
                        ui_domain = metadata.get("ui_domain")
                
                # Refresh from HubSpot when portal/ui domain not cached (OAuth tokens lack pat-eu1 prefix)
                if not portal_id or not ui_domain:
                    try:
                        account_ctx = await resolve_account_context(self.client)
                        portal_id = portal_id or account_ctx.portal_id
                        if account_ctx.region and account_ctx.region != "na1":
                            region = account_ctx.region
                        elif not metadata.get("region"):
                            region = account_ctx.region or region
                        if account_ctx.ui_domain:
                            ui_domain = account_ctx.ui_domain
                        if portal_id and self.supabase:
                            self.supabase.table("crm_connections").update({
                                "metadata": {
                                    **metadata,
                                    "portal_id": portal_id,
                                    "region": region,
                                    "ui_domain": ui_domain,
                                }
                            }).eq("id", str(connection_id)).execute()
                    except Exception:
                        pass
                
                if portal_id:
                    result.deal_url = build_deal_record_url(
                        portal_id,
                        deal_id,
                        ui_domain=ui_domain,
                        region=region or "na1",
                    )
            
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

