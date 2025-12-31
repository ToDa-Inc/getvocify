"""
Deal operations service for HubSpot.

Handles creating, updating, and finding deals with proper
field mapping from MemoExtraction to HubSpot properties.
Includes pipeline stage resolution.
"""

from .client import HubSpotClient
from .exceptions import HubSpotError
from .types import HubSpotDeal, CreateObjectRequest, UpdateObjectRequest
from .search import HubSpotSearchService
from .schema import HubSpotSchemaService
from app.models.memo import MemoExtraction


class HubSpotDealService:
    """
    Service for managing HubSpot deals.
    
    Features:
    - Field mapping from MemoExtraction to HubSpot properties
    - Pipeline stage resolution (name → stage ID)
    - Date formatting (ISO → HubSpot timestamp)
    - Deal name generation
    - Create or update logic
    """
    
    OBJECT_TYPE = "deals"
    
    def __init__(
        self,
        client: HubSpotClient,
        search: HubSpotSearchService,
        schema: HubSpotSchemaService,
    ):
        self.client = client
        self.search = search
        self.schema = schema
    
    def _generate_deal_name(
        self,
        extraction: MemoExtraction,
        contact_name: str | None = None,
    ) -> str:
        """
        Generate a deal name from extraction data.
        
        Priority:
        1. Company name + " Deal"
        2. Contact name + " Deal"
        3. "New Deal"
        
        Args:
            extraction: MemoExtraction data
            contact_name: Optional contact name for fallback
            
        Returns:
            Deal name string
        """
        if extraction.companyName:
            return f"{extraction.companyName} Deal"
        elif contact_name:
            return f"{contact_name} Deal"
        elif extraction.contactName:
            return f"{extraction.contactName} Deal"
        else:
            return "New Deal"
    
    def _to_hubspot_timestamp(self, iso_date: str) -> str | None:
        """
        Convert ISO date string to HubSpot timestamp (milliseconds since epoch).
        
        Args:
            iso_date: ISO format date string (YYYY-MM-DD)
            
        Returns:
            Timestamp string in milliseconds, or None if invalid
        """
        try:
            from datetime import datetime
            
            # Parse ISO date
            dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
            
            # Convert to milliseconds since epoch
            timestamp_ms = int(dt.timestamp() * 1000)
            
            return str(timestamp_ms)
            
        except Exception:
            return None
    
    async def _resolve_stage_id(self, stage_name: str) -> str | None:
        """
        Resolve pipeline stage name to stage ID.
        
        Args:
            stage_name: Stage name (e.g., "Qualification")
            
        Returns:
            Stage ID if found, None otherwise
        """
        if not stage_name:
            return None
        
        try:
            schema = await self.schema.get_deal_schema()
            
            # Search through all pipelines and stages
            for pipeline in schema.pipelines:
                for stage in pipeline.stages:
                    if stage.label.lower() == stage_name.strip().lower():
                        return stage.id
            
            return None
            
        except Exception:
            return None
    
    def map_extraction_to_properties(
        self,
        extraction: MemoExtraction,
        deal_name: str | None = None,
    ) -> dict[str, any]:
        """
        Convert MemoExtraction fields to HubSpot deal properties.
        
        Args:
            extraction: MemoExtraction from voice memo
            deal_name: Optional deal name (will generate if not provided)
            
        Returns:
            Dictionary of HubSpot property names to values
        """
        properties: dict[str, any] = {}
        
        # Deal name (required)
        properties["dealname"] = deal_name or self._generate_deal_name(extraction)
        
        # Amount
        if extraction.dealAmount is not None:
            properties["amount"] = str(extraction.dealAmount)
        
        # Currency - Only set if provided and not just a default guess
        # Note: We omit this by default to use the HubSpot Portal's default currency
        # to avoid "INVALID_OPTION" errors for unsupported currency codes.
        # if extraction.dealCurrency:
        #     properties["deal_currency_code"] = extraction.dealCurrency
        
        # Close date
        if extraction.closeDate:
            timestamp = self._to_hubspot_timestamp(extraction.closeDate)
            if timestamp:
                properties["closedate"] = timestamp
        
        # Description (summary)
        if extraction.summary:
            properties["description"] = extraction.summary
        
        return properties
    
    async def map_extraction_to_properties_with_stage(
        self,
        extraction: MemoExtraction,
        deal_name: str | None = None,
    ) -> dict[str, any]:
        """
        Convert MemoExtraction to HubSpot properties, including stage resolution.
        
        This is the async version that resolves stage IDs.
        
        Args:
            extraction: MemoExtraction from voice memo
            deal_name: Optional deal name
            
        Returns:
            Dictionary of HubSpot property names to values
        """
        properties = self.map_extraction_to_properties(extraction, deal_name)
        
        # Resolve deal stage
        if extraction.dealStage:
            stage_id = await self._resolve_stage_id(extraction.dealStage)
            if stage_id:
                properties["dealstage"] = stage_id
        
        return properties
    
    async def get(self, deal_id: str) -> HubSpotDeal:
        """
        Get a deal by ID.
        
        Args:
            deal_id: HubSpot deal ID
            
        Returns:
            HubSpotDeal object
            
        Raises:
            HubSpotNotFoundError if deal doesn't exist
            HubSpotError for other errors
        """
        try:
            response = await self.client.get(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{deal_id}",
                params={
                    "properties": "dealname,amount,deal_currency_code,dealstage,closedate,description"
                },
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotDeal(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to get deal: {str(e)}")
    
    async def create(
        self,
        properties: dict[str, any],
        contact_id: str | None = None,
        company_id: str | None = None,
    ) -> HubSpotDeal:
        """
        Create a new deal with optional associations.
        
        Args:
            properties: Dictionary of HubSpot property names to values
            contact_id: Optional contact ID to associate
            company_id: Optional company ID to associate
            
        Returns:
            Created HubSpotDeal
            
        Raises:
            HubSpotError for API errors
        """
        if not properties.get("dealname"):
            raise HubSpotError("Deal name is required")
        
        request = CreateObjectRequest(properties=properties)
        
        # Add associations if provided
        if contact_id:
            request.associations.append(
                {"to_object_id": contact_id, "association_type": "3"}
            )
        if company_id:
            request.associations.append(
                {"to_object_id": company_id, "association_type": "5"}
            )
        
        try:
            response = await self.client.post(
                f"/crm/v3/objects/{self.OBJECT_TYPE}",
                data=request.model_dump(exclude_none=True, by_alias=True),
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotDeal(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to create deal: {str(e)}")
    
    async def update(
        self,
        deal_id: str,
        properties: dict[str, any],
    ) -> HubSpotDeal:
        """
        Update an existing deal.
        
        Args:
            deal_id: HubSpot deal ID
            properties: Dictionary of properties to update
            
        Returns:
            Updated HubSpotDeal
            
        Raises:
            HubSpotNotFoundError if deal doesn't exist
            HubSpotError for other errors
        """
        request = UpdateObjectRequest(properties=properties)
        
        try:
            response = await self.client.patch(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{deal_id}",
                data=request.model_dump(exclude_none=True, by_alias=True),
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotDeal(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to update deal: {str(e)}")
    
    async def create_or_update(
        self,
        extraction: MemoExtraction,
        contact_id: str | None = None,
        company_id: str | None = None,
    ) -> HubSpotDeal:
        """
        Create a new deal based on extraction data.
        
        Note: We always create a new deal (don't update existing).
        This matches the product principle: one voice memo = one CRM update.
        
        Args:
            extraction: MemoExtraction with deal data
            contact_id: Optional contact ID to associate
            company_id: Optional company ID to associate
            
        Returns:
            Created HubSpotDeal
            
        Raises:
            HubSpotError for API errors
        """
        deal_name = self._generate_deal_name(
            extraction,
            contact_name=None,  # Could fetch contact name if needed
        )
        
        properties = await self.map_extraction_to_properties_with_stage(
            extraction,
            deal_name=deal_name,
        )
        
        return await self.create(properties, contact_id, company_id)

