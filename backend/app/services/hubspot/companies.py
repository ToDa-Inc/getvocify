"""
Company operations service for HubSpot.

Handles creating, updating, and finding companies with proper
field mapping from MemoExtraction to HubSpot properties.
"""

from typing import Any, Optional

from .client import HubSpotClient
from .exceptions import HubSpotError
from .types import HubSpotCompany, CreateObjectRequest, UpdateObjectRequest
from .search import HubSpotSearchService
from app.models.memo import MemoExtraction


class HubSpotCompanyService:
    """
    Service for managing HubSpot companies.
    
    Features:
    - Field mapping from MemoExtraction to HubSpot properties
    - Deduplication by name
    - Create or update logic
    """
    
    OBJECT_TYPE = "companies"
    
    def __init__(self, client: HubSpotClient, search: HubSpotSearchService):
        self.client = client
        self.search = search
    
    def map_extraction_to_properties(
        self,
        extraction: MemoExtraction,
    ) -> dict[str, Any]:
        """
        Convert MemoExtraction fields to HubSpot company properties.
        
        Args:
            extraction: MemoExtraction from voice memo
            
        Returns:
            Dictionary of HubSpot property names to values
        """
        properties: dict[str, Any] = {}
        
        # Company name (required)
        if extraction.companyName:
            properties["name"] = extraction.companyName.strip()
        
        # Domain (if we can extract it from email or other sources)
        # For MVP, we'll skip domain extraction
        
        return properties
    
    async def get(self, company_id: str, properties: Optional[list[str]] = None) -> HubSpotCompany:
        """
        Get a company by ID.
        """
        props = properties or ["name", "domain"]
        try:
            response = await self.client.get(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{company_id}",
                params={"properties": ",".join(props)},
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotCompany(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to get company: {str(e)}")
    
    async def create(self, properties: dict[str, Any]) -> HubSpotCompany:
        """
        Create a new company.
        
        Args:
            properties: Dictionary of HubSpot property names to values
            
        Returns:
            Created HubSpotCompany
            
        Raises:
            HubSpotError for API errors
        """
        if not properties.get("name"):
            raise HubSpotError("Company name is required")
        
        request = CreateObjectRequest(properties=properties)
        
        try:
            response = await self.client.post(
                f"/crm/v3/objects/{self.OBJECT_TYPE}",
                data=request.model_dump(exclude_none=True, by_alias=True),
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotCompany(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to create company: {str(e)}")
    
    async def update(
        self,
        company_id: str,
        properties: dict[str, Any],
    ) -> HubSpotCompany:
        """
        Update an existing company.
        
        Args:
            company_id: HubSpot company ID
            properties: Dictionary of properties to update
            
        Returns:
            Updated HubSpotCompany
            
        Raises:
            HubSpotNotFoundError if company doesn't exist
            HubSpotError for other errors
        """
        request = UpdateObjectRequest(properties=properties)
        
        try:
            response = await self.client.patch(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{company_id}",
                data=request.model_dump(exclude_none=True, by_alias=True),
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotCompany(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to update company: {str(e)}")
    
    async def create_or_update(
        self,
        extraction: MemoExtraction,
        allowed_fields: Optional[list[str]] = None,
    ) -> Optional[HubSpotCompany]:
        """
        Create or update a company based on extraction data.
        
        Logic:
        1. If company name exists, search for existing company
        2. If found, update allowlisted properties when present
        3. If not found, create new company
        4. If no company name, return None
        """
        from .object_properties import company_properties_from_extraction

        if not extraction.companyName:
            return None
        
        identity = self.map_extraction_to_properties(extraction)
        properties = company_properties_from_extraction(
            extraction,
            allowed_fields=allowed_fields,
            identity_props=identity,
        )
        if not properties.get("name") and extraction.companyName:
            properties["name"] = extraction.companyName.strip()
        
        existing = await self.search.find_company_by_name(extraction.companyName)
        
        if existing:
            update_props = {k: v for k, v in properties.items() if k != "name" and v}
            if update_props:
                return await self.update(existing.id, update_props)
            return existing
        return await self.create(properties)

