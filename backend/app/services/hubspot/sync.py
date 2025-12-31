"""
Main synchronization orchestrator for HubSpot.

Orchestrates the complete flow of syncing a voice memo extraction
to HubSpot CRM, including creating/updating contacts, companies, deals,
and associations.
"""

from uuid import UUID

from .client import HubSpotClient
from .exceptions import HubSpotAuthError, HubSpotScopeError, HubSpotError
from .types import SyncResult
from .contacts import HubSpotContactService
from .companies import HubSpotCompanyService
from .deals import HubSpotDealService
from .associations import HubSpotAssociationService
from app.models.memo import MemoExtraction
from app.services.crm_updates import CRMUpdatesService


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
        crm_updates: CRMUpdatesService,
    ):
        self.client = client
        self.contacts = contacts
        self.companies = companies
        self.deals = deals
        self.associations = associations
        self.crm_updates = crm_updates
    
    def _filter_properties(
        self,
        properties: dict[str, any],
        allowed_fields: list[str],
    ) -> dict[str, any]:
        """
        Filter properties to only include allowed fields.
        
        Args:
            properties: Dictionary of HubSpot properties
            allowed_fields: List of allowed field names
            
        Returns:
            Filtered properties dictionary
        """
        return {k: v for k, v in properties.items() if k in allowed_fields}
    
    async def sync_memo(
        self,
        memo_id: UUID | str,
        user_id: str,
        connection_id: UUID | str,
        extraction: MemoExtraction,
        deal_id: str | None = None,
        is_new_deal: bool = False,
        allowed_fields: list[str] | None = None,
    ) -> SyncResult:
        """
        Sync a voice memo extraction to HubSpot CRM.
        
        Supports both creating new deals and updating existing deals.
        Filters properties based on allowed_fields whitelist.
        
        Args:
            memo_id: Voice memo ID
            user_id: User ID
            connection_id: CRM connection ID
            extraction: MemoExtraction with extracted data
            deal_id: Optional deal ID to update (None = create new)
            is_new_deal: Whether to create a new deal (if deal_id is None)
            allowed_fields: List of field names AI is allowed to update
            
        Returns:
            SyncResult with success status and created/updated object IDs
        """
        result = SyncResult(memo_id=str(memo_id))
        
        # Default allowed fields if not provided
        if allowed_fields is None:
            allowed_fields = ["dealname", "amount", "description", "closedate"]
        
        company_id = None
        contact_id = None
        
        try:
            # Step 1: Company (if we have company name and auto-create enabled)
            # Note: For update mode, we still create/update company if needed
            if extraction.companyName:
                try:
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
            
            # Step 2: Contact (if we have email or name)
            if extraction.contactEmail or extraction.contactName:
                try:
                    contact = await self.contacts.create_or_update(extraction)
                    if contact:
                        contact_id = contact.id
                        result.contact_id = contact_id
                        
                        await self.crm_updates.create_update(
                            memo_id=str(memo_id),
                            user_id=user_id,
                            crm_connection_id=str(connection_id),
                            action_type="upsert_contact",
                            resource_type="contact",
                            data={"contact_id": contact_id, "email": extraction.contactEmail},
                        )
                except Exception as e:
                    # Log error but continue
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
                    # UPDATE MODE: Update existing deal
                    # Map extraction to properties
                    deal_properties = await self.deals.map_extraction_to_properties_with_stage(extraction)
                    
                    # Filter to only allowed fields
                    filtered_properties = self._filter_properties(deal_properties, allowed_fields)
                    
                    if not filtered_properties:
                        # No allowed fields to update
                        result.error = "No allowed fields to update"
                        result.error_code = "NO_FIELDS_TO_UPDATE"
                        return result
                    
                    # Update deal
                    deal = await self.deals.update(deal_id, filtered_properties)
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
            
            # Step 5: Associate deal → contact, deal → company (only for new deals)
            if is_new_deal or not deal_id:
                if contact_id:
                    try:
                        await self.associations.associate_deal_to_contact(deal_id, contact_id)
                    except Exception:
                        # Log but don't fail
                        pass
                
                if company_id:
                    try:
                        await self.associations.associate_deal_to_company(deal_id, company_id)
                    except Exception:
                        # Log but don't fail
                        pass
            
            # Success!
            result.success = True
            
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

