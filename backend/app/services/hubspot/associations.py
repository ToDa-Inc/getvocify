"""
Association management service for HubSpot.

Handles creating relationships between HubSpot objects
(contacts, companies, deals).
"""

from .client import HubSpotClient
from .exceptions import HubSpotError


class HubSpotAssociationService:
    """
    Service for managing associations between HubSpot objects.
    
    Common association types:
    - Contact to Company (type 1)
    - Company to Contact (type 2)
    - Deal to Contact (type 3)
    - Contact to Deal (type 4)
    - Deal to Company (type 5)
    - Company to Deal (type 6)
    """
    
    # Standard association type IDs
    CONTACT_TO_COMPANY = "1"
    COMPANY_TO_CONTACT = "2"
    DEAL_TO_CONTACT = "3"
    CONTACT_TO_DEAL = "4"
    DEAL_TO_COMPANY = "5"
    COMPANY_TO_DEAL = "6"
    
    def __init__(self, client: HubSpotClient):
        self.client = client
    
    async def create_association(
        self,
        from_object_type: str,
        from_object_id: str,
        to_object_type: str,
        to_object_id: str,
        association_type: str,
    ) -> None:
        """
        Create an association between two objects.
        
        Args:
            from_object_type: Source object type (e.g., "contacts")
            from_object_id: Source object ID
            to_object_type: Target object type (e.g., "companies")
            to_object_id: Target object ID
            association_type: Association type ID (e.g., "1" for contact-to-company)
            
        Raises:
            HubSpotError for API errors
        """
        try:
            # HubSpot v4 associations API
            # Format: PUT /crm/v4/objects/{fromObjectType}/{fromObjectId}/associations/{toObjectType}/{toObjectId}/{associationType}
            # Body: [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": association_type}]
            type_id = int(association_type) if isinstance(association_type, str) else association_type
            await self.client.put(
                f"/crm/v4/objects/{from_object_type}/{from_object_id}/associations/{to_object_type}/{to_object_id}",
                data=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": type_id}],
            )
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(
                f"Failed to create association from {from_object_type}:{from_object_id} "
                f"to {to_object_type}:{to_object_id}: {str(e)}"
            )
    
    async def associate_contact_to_company(
        self,
        contact_id: str,
        company_id: str,
    ) -> None:
        """
        Associate a contact to a company.
        
        Args:
            contact_id: HubSpot contact ID
            company_id: HubSpot company ID
            
        Raises:
            HubSpotError for API errors
        """
        await self.create_association(
            from_object_type="contacts",
            from_object_id=contact_id,
            to_object_type="companies",
            to_object_id=company_id,
            association_type=self.CONTACT_TO_COMPANY,
        )
    
    async def associate_deal_to_contact(
        self,
        deal_id: str,
        contact_id: str,
    ) -> None:
        """
        Associate a deal to a contact.
        
        Args:
            deal_id: HubSpot deal ID
            contact_id: HubSpot contact ID
            
        Raises:
            HubSpotError for API errors
        """
        await self.create_association(
            from_object_type="deals",
            from_object_id=deal_id,
            to_object_type="contacts",
            to_object_id=contact_id,
            association_type=self.DEAL_TO_CONTACT,
        )
    
    async def associate_deal_to_company(
        self,
        deal_id: str,
        company_id: str,
    ) -> None:
        """
        Associate a deal to a company.
        
        Args:
            deal_id: HubSpot deal ID
            company_id: HubSpot company ID
            
        Raises:
            HubSpotError for API errors
        """
        await self.create_association(
            from_object_type="deals",
            from_object_id=deal_id,
            to_object_type="companies",
            to_object_id=company_id,
            association_type=self.DEAL_TO_COMPANY,
        )
    
    async def get_associations(
        self,
        object_type: str,
        object_id: str,
        to_object_type: str,
    ) -> list[str]:
        """
        Get all associations from an object to another object type.
        
        Args:
            object_type: Source object type
            object_id: Source object ID
            to_object_type: Target object type
            
        Returns:
            List of associated object IDs
            
        Raises:
            HubSpotError for API errors
        """
        try:
            response = await self.client.get(
                f"/crm/v4/objects/{object_type}/{object_id}/associations/{to_object_type}",
            )
            
            if not response or "results" not in response:
                return []
            
            # Extract IDs from results
            return [result.get("id", "") for result in response.get("results", [])]
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(
                f"Failed to get associations from {object_type}:{object_id} "
                f"to {to_object_type}: {str(e)}"
            )

