"""
Search and deduplication service for HubSpot objects.

Finds existing records before creating duplicates.
"""

from typing import Literal

from .client import HubSpotClient
from .exceptions import HubSpotError
from .types import (
    HubSpotContact,
    HubSpotCompany,
    HubSpotDeal,
    SearchRequest,
    Filter,
    FilterGroup,
)


class HubSpotSearchService:
    """
    Search and deduplication logic for HubSpot objects.
    
    Provides methods to find existing records by:
    - Email (contacts)
    - Name (companies, deals)
    - Domain (companies)
    """
    
    # Object type IDs
    CONTACTS = "contacts"
    COMPANIES = "companies"
    DEALS = "deals"
    
    def __init__(self, client: HubSpotClient):
        self.client = client
    
    async def search(
        self,
        object_type: Literal["contacts", "companies", "deals"],
        filters: list[Filter],
        properties: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, any]]:
        """
        Search for objects using filters.
        
        Args:
            object_type: Object type to search
            filters: List of filter conditions (AND logic)
            properties: Properties to return (default: all)
            limit: Maximum results (1-100)
            
        Returns:
            List of matching objects
            
        Raises:
            HubSpotError if search fails
        """
        filter_group = FilterGroup(filters=filters)
        request = SearchRequest(
            filterGroups=[filter_group],
            properties=properties or [],
            limit=min(limit, 100),
        )
        
        try:
            response = await self.client.post(
                f"/crm/v3/objects/{object_type}/search",
                data=request.model_dump(exclude_none=True, by_alias=True),
            )
            
            if not response or "results" not in response:
                return []
            
            return response["results"]
            
        except Exception as e:
            raise HubSpotError(f"Search failed for {object_type}: {str(e)}")
    
    async def find_contact_by_email(self, email: str) -> HubSpotContact | None:
        """
        Find contact by email address.
        
        Args:
            email: Email address to search for
            
        Returns:
            HubSpotContact if found, None otherwise
        """
        if not email or not email.strip():
            return None
        
        filters = [
            Filter(
                propertyName="email",
                operator="EQ",
                value=email.strip().lower(),
            )
        ]
        
        results = await self.search(
            self.CONTACTS,
            filters,
            properties=["email", "firstname", "lastname", "phone", "jobtitle"],
            limit=1,
        )
        
        if not results:
            return None
        
        try:
            return HubSpotContact(**results[0])
        except Exception:
            return None
    
    async def find_company_by_name(self, name: str) -> HubSpotCompany | None:
        """
        Find company by name (exact match).
        
        Args:
            name: Company name to search for
            
        Returns:
            HubSpotCompany if found, None otherwise
        """
        if not name or not name.strip():
            return None
        
        filters = [
            Filter(
                propertyName="name",
                operator="EQ",
                value=name.strip(),
            )
        ]
        
        results = await self.search(
            self.COMPANIES,
            filters,
            properties=["name", "domain"],
            limit=1,
        )
        
        if not results:
            return None
        
        try:
            return HubSpotCompany(**results[0])
        except Exception:
            return None
    
    async def find_company_by_domain(self, domain: str) -> HubSpotCompany | None:
        """
        Find company by domain name.
        
        Args:
            domain: Domain name (e.g., "example.com")
            
        Returns:
            HubSpotCompany if found, None otherwise
        """
        if not domain or not domain.strip():
            return None
        
        # Normalize domain (remove protocol, www, trailing slash)
        domain = domain.strip().lower()
        domain = domain.replace("https://", "").replace("http://", "")
        domain = domain.replace("www.", "")
        domain = domain.split("/")[0]
        
        filters = [
            Filter(
                propertyName="domain",
                operator="EQ",
                value=domain,
            )
        ]
        
        results = await self.search(
            self.COMPANIES,
            filters,
            properties=["name", "domain"],
            limit=1,
        )
        
        if not results:
            return None
        
        try:
            return HubSpotCompany(**results[0])
        except Exception:
            return None
    
    async def find_deal_by_name(
        self,
        deal_name: str,
        contact_id: str | None = None,
    ) -> HubSpotDeal | None:
        """
        Find deal by name, optionally filtered by contact.
        
        Args:
            deal_name: Deal name to search for
            contact_id: Optional contact ID to filter by
            
        Returns:
            HubSpotDeal if found, None otherwise
        """
        if not deal_name:
            return None
            
        filters = [
            Filter(
                propertyName="dealname",
                operator="EQ",
                value=deal_name.strip(),
            )
        ]
        
        # Note: Filtering by association (contact_id) requires
        # a different approach - we'd need to search deals and then
        # filter by association. For MVP, we'll just search by name.
        
        results = await self.search(
            self.DEALS,
            filters,
            properties=["dealname", "amount", "dealstage", "closedate"],
            limit=1,
        )
        
        if not results:
            return None
        
        try:
            return HubSpotDeal(**results[0])
        except Exception:
            return None

    async def search_deals_by_query(
        self,
        query: str,
        limit: int = 10,
        pipeline_id: str | None = None,
    ) -> list[dict[str, any]]:
        """
        Search for deals using a text query (matches name).
        """
        if not query or not query.strip():
            return []
            
        filters = [
            Filter(
                propertyName="dealname",
                operator="CONTAINS_TOKEN",
                value=query.strip(),
            )
        ]
        
        if pipeline_id:
            filters.append(
                Filter(
                    propertyName="pipeline",
                    operator="EQ",
                    value=pipeline_id,
                )
            )
            
        return await self.search(
            self.DEALS,
            filters,
            properties=["dealname", "amount", "dealstage", "closedate", "hs_lastmodifieddate"],
            limit=limit,
        )

