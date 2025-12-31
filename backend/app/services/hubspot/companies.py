"""
Company operations service for HubSpot.

Handles creating, updating, and finding companies with proper
field mapping from MemoExtraction to HubSpot properties.
"""

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
    ) -> dict[str, any]:
        """
        Convert MemoExtraction fields to HubSpot company properties.
        
        Args:
            extraction: MemoExtraction from voice memo
            
        Returns:
            Dictionary of HubSpot property names to values
        """
        properties: dict[str, any] = {}
        
        # Company name (required)
        if extraction.companyName:
            properties["name"] = extraction.companyName.strip()
        
        # Domain (if we can extract it from email or other sources)
        # For MVP, we'll skip domain extraction
        
        return properties
    
    async def get(self, company_id: str) -> HubSpotCompany:
        """
        Get a company by ID.
        
        Args:
            company_id: HubSpot company ID
            
        Returns:
            HubSpotCompany object
            
        Raises:
            HubSpotNotFoundError if company doesn't exist
            HubSpotError for other errors
        """
        try:
            response = await self.client.get(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{company_id}",
                params={"properties": "name,domain"},
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotCompany(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to get company: {str(e)}")
    
    async def create(self, properties: dict[str, any]) -> HubSpotCompany:
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
        properties: dict[str, any],
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
    ) -> HubSpotCompany | None:
        """
        Create or update a company based on extraction data.
        
        Logic:
        1. If company name exists, search for existing company
        2. If found, update it (if needed)
        3. If not found, create new company
        4. If no company name, return None
        
        Args:
            extraction: MemoExtraction with company data
            
        Returns:
            HubSpotCompany if created/updated, None if no company name
            
        Raises:
            HubSpotError for API errors
        """
        # Can't create company without name
        if not extraction.companyName:
            return None
        
        properties = self.map_extraction_to_properties(extraction)
        
        # Try to find existing company by name
        existing = await self.search.find_company_by_name(extraction.companyName)
        
        if existing:
            # Update existing company (only if we have new data)
            # For MVP, we'll just return existing company
            # In future, we could merge data intelligently
            return existing
        else:
            # Create new company
            return await self.create(properties)

