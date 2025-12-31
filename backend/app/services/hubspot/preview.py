"""
Approval preview service for showing proposed CRM updates.
"""

from uuid import UUID
from typing import Optional
from app.models.memo import MemoExtraction
from app.models.approval import ApprovalPreview, ProposedUpdate, DealMatch
from .client import HubSpotClient
from .exceptions import HubSpotError
from .deals import HubSpotDealService
from .schema import HubSpotSchemaService


class HubSpotPreviewService:
    """
    Builds approval previews showing what will be updated in HubSpot.
    
    Compares extraction data to existing deal properties and generates
    a list of proposed changes.
    """
    
    def __init__(
        self,
        client: HubSpotClient,
        deal_service: HubSpotDealService,
        schema_service: HubSpotSchemaService,
    ):
        self.client = client
        self.deals = deal_service
        self.schema = schema_service
    
    async def build_preview(
        self,
        memo_id: UUID,
        transcript: str,
        extraction: MemoExtraction,
        matched_deals: list[DealMatch],
        selected_deal_id: Optional[str] = None,
        allowed_fields: Optional[list[str]] = None,
    ) -> ApprovalPreview:
        """
        Build approval preview with proposed updates.
        
        Args:
            memo_id: Memo ID
            transcript: Full transcript text
            extraction: Extracted data
            matched_deals: List of matched deals from matching service
            selected_deal_id: Deal ID user selected (None = create new)
            allowed_fields: List of field names user allows AI to update
            
        Returns:
            ApprovalPreview with proposed changes
        """
        # Get transcript summary (first 200 chars)
        transcript_summary = transcript[:200] + "..." if len(transcript) > 200 else transcript
        
        # Default allowed fields if not provided
        if allowed_fields is None:
            allowed_fields = ["dealname", "amount", "description", "closedate"]
        
        # Determine if creating new deal or updating existing
        is_new_deal = selected_deal_id is None
        
        selected_deal: Optional[DealMatch] = None
        proposed_updates: list[ProposedUpdate] = []
        
        if is_new_deal:
            # Creating new deal - no current values
            proposed_updates = self._build_new_deal_updates(extraction, allowed_fields)
        else:
            # Updating existing deal - fetch current values
            # Try to find in matched deals first
            selected_deal = next(
                (d for d in matched_deals if d.deal_id == selected_deal_id),
                None
            )
            
            # If not in matched deals (manual selection), fetch basic info
            if not selected_deal:
                try:
                    deal = await self.deals.get(selected_deal_id)
                    selected_deal = DealMatch(
                        deal_id=deal.id,
                        deal_name=deal.properties.get("dealname", "Unknown Deal"),
                        match_reason="Manual Selection",
                        match_confidence=1.0,
                        stage=deal.properties.get("dealstage"),
                        amount=deal.properties.get("amount"),
                        last_updated=deal.properties.get("hs_lastmodifieddate", "")
                    )
                except Exception:
                    # Fallback if deal not found
                    pass
            
            if selected_deal:
                proposed_updates = await self._build_update_preview(
                    selected_deal_id,
                    extraction,
                    allowed_fields,
                )
        
        return ApprovalPreview(
            memo_id=memo_id,
            transcript_summary=transcript_summary,
            matched_deals=matched_deals,
            selected_deal=selected_deal,
            is_new_deal=is_new_deal,
            proposed_updates=proposed_updates,
        )
    
    def _build_new_deal_updates(
        self,
        extraction: MemoExtraction,
        allowed_fields: list[str],
    ) -> list[ProposedUpdate]:
        """Build proposed updates for a new deal"""
        updates = []
        
        # Get schema for field labels
        # Note: We'll need to fetch this, but for MVP we'll use common field names
        field_labels = {
            "dealname": "Deal Name",
            "amount": "Amount",
            "description": "Description",
            "closedate": "Close Date",
        }
        
        # Deal name
        if "dealname" in allowed_fields and extraction.companyName:
            deal_name = f"{extraction.companyName} Deal"
            updates.append(ProposedUpdate(
                field_name="dealname",
                field_label=field_labels.get("dealname", "Deal Name"),
                current_value=None,
                new_value=deal_name,
                extraction_confidence=extraction.confidence.get("fields", {}).get("companyName", 0.8),
            ))
        
        # Amount
        if "amount" in allowed_fields and extraction.dealAmount is not None:
            updates.append(ProposedUpdate(
                field_name="amount",
                field_label=field_labels.get("amount", "Amount"),
                current_value=None,
                new_value=str(extraction.dealAmount),
                extraction_confidence=extraction.confidence.get("fields", {}).get("dealAmount", 0.7),
            ))
        
        # Description (summary)
        if "description" in allowed_fields and extraction.summary:
            updates.append(ProposedUpdate(
                field_name="description",
                field_label=field_labels.get("description", "Description"),
                current_value=None,
                new_value=extraction.summary,
                extraction_confidence=extraction.confidence.get("fields", {}).get("summary", 0.8),
            ))
        
        # Close date
        if "closedate" in allowed_fields and extraction.closeDate:
            updates.append(ProposedUpdate(
                field_name="closedate",
                field_label=field_labels.get("closedate", "Close Date"),
                current_value=None,
                new_value=extraction.closeDate,
                extraction_confidence=extraction.confidence.get("fields", {}).get("closeDate", 0.7),
            ))
        
        return updates
    
    async def _build_update_preview(
        self,
        deal_id: str,
        extraction: MemoExtraction,
        allowed_fields: list[str],
    ) -> list[ProposedUpdate]:
        """Build proposed updates for an existing deal"""
        updates = []
        
        try:
            # Fetch current deal
            current_deal = await self.deals.get(deal_id)
            current_props = current_deal.properties
            
            # Field labels
            field_labels = {
                "dealname": "Deal Name",
                "amount": "Amount",
                "description": "Description",
                "closedate": "Close Date",
            }
            
            # Compare extraction to current values
            # Deal name
            if "dealname" in allowed_fields and extraction.companyName:
                current_name = current_props.get("dealname")
                new_name = f"{extraction.companyName} Deal"
                if current_name != new_name:
                    updates.append(ProposedUpdate(
                        field_name="dealname",
                        field_label=field_labels.get("dealname", "Deal Name"),
                        current_value=current_name,
                        new_value=new_name,
                        extraction_confidence=extraction.confidence.get("fields", {}).get("companyName", 0.8),
                    ))
            
            # Amount
            if "amount" in allowed_fields and extraction.dealAmount is not None:
                current_amount = current_props.get("amount")
                new_amount = str(extraction.dealAmount)
                if current_amount != new_amount:
                    updates.append(ProposedUpdate(
                        field_name="amount",
                        field_label=field_labels.get("amount", "Amount"),
                        current_value=current_amount,
                        new_value=new_amount,
                        extraction_confidence=extraction.confidence.get("fields", {}).get("dealAmount", 0.7),
                    ))
            
            # Description
            if "description" in allowed_fields and extraction.summary:
                current_desc = current_props.get("description")
                # Append to description if it exists, otherwise set it
                if current_desc:
                    new_desc = f"{current_desc}\n\n{extraction.summary}"
                else:
                    new_desc = extraction.summary
                
                if current_desc != new_desc:
                    updates.append(ProposedUpdate(
                        field_name="description",
                        field_label=field_labels.get("description", "Description"),
                        current_value=current_desc or "(empty)",
                        new_value=new_desc,
                        extraction_confidence=extraction.confidence.get("fields", {}).get("summary", 0.8),
                    ))
            
            # Close date
            if "closedate" in allowed_fields and extraction.closeDate:
                current_date = current_props.get("closedate")
                if current_date != extraction.closeDate:
                    updates.append(ProposedUpdate(
                        field_name="closedate",
                        field_label=field_labels.get("closedate", "Close Date"),
                        current_value=current_date,
                        new_value=extraction.closeDate,
                        extraction_confidence=extraction.confidence.get("fields", {}).get("closeDate", 0.7),
                    ))
            
        except Exception as e:
            # If we can't fetch current deal, return empty updates
            # The sync will handle the error
            pass
        
        return updates

