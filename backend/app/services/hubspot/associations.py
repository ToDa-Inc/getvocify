"""
Association management service for HubSpot.

Handles creating relationships between HubSpot objects
(contacts, companies, deals).
"""

import logging

from .client import HubSpotClient
from .exceptions import HubSpotError

logger = logging.getLogger(__name__)


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

    # Note (activity) association types - one-directional (note -> object).
    # Required explicitly in the `associations` array when creating a note via
    # POST /crm/v3/objects/notes (unlike the default-association PUT endpoint
    # above, which infers the type). Verified against HubSpot's default
    # associationTypeId table (developers.hubspot.com/docs/api-reference/.../
    # crm/associations/associate-records/guide, "Note to object" section).
    NOTE_TO_CONTACT = 202
    NOTE_TO_COMPANY = 190
    NOTE_TO_DEAL = 214
    
    def __init__(self, client: HubSpotClient):
        self.client = client
    
    # HubSpot v4 uses singular object types: contact, company, deal
    _SINGULAR = {"contacts": "contact", "companies": "company", "deals": "deal"}

    async def create_association(
        self,
        from_object_type: str,
        from_object_id: str,
        to_object_type: str,
        to_object_id: str,
        association_type: str = None,
    ) -> None:
        """
        Create an unlabeled association between two objects.
        
        Uses HubSpot v4 default association endpoint:
        PUT /crm/v4/objects/{from}/associations/default/{to}
        
        Args:
            from_object_type: Source object type (e.g., "deals" or "deal")
            from_object_id: Source object ID
            to_object_type: Target object type (e.g., "contacts" or "contact")
            to_object_id: Target object ID
            association_type: Unused (kept for API compatibility)
            
        Raises:
            HubSpotError for API errors
        """
        try:
            from_type = self._SINGULAR.get(from_object_type, from_object_type.rstrip("s"))
            to_type = self._SINGULAR.get(to_object_type, to_object_type.rstrip("s"))
            url = (
                f"/crm/v4/objects/{from_type}/{from_object_id}/associations/default/"
                f"{to_type}/{to_object_id}"
            )
            await self.client.put(url, data=None)
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

            raw_results = response.get("results", [])

            # This single-object GET returns MultiAssociatedObjectWithLabel per HubSpot's
            # own OpenAPI schema: `toObjectId` sits directly on each result item, not
            # under `objectId`/`id`, and not nested under a `to[]` array. That last shape
            # belongs to the *batch* associations endpoints, not this one - a previous
            # version of this parser checked for it here anyway, unverified against the
            # real response, and it silently matched nothing: this call always returned
            # an empty list even when HubSpot had associations to report, for every
            # object type pair that ever went through this method (contacts→companies,
            # deals→contacts, deals→companies, etc.) - see contact_identity.py's
            # deal-matching regression this was found from. `objectId`/`id`/`to[]` are
            # kept below as a defensive fallback only, not because they're expected here.
            ids = []
            for result in raw_results:
                oid = (
                    result.get("toObjectId")
                    or result.get("objectId")
                    or result.get("id")
                )
                if oid is not None:
                    ids.append(str(oid))
                    continue
                for to_item in result.get("to", []):
                    oid = to_item.get("toObjectId")
                    if oid is not None:
                        ids.append(str(oid))

            if raw_results and not ids:
                # HubSpot returned associations but none of the known shapes matched -
                # this is the exact signature of a parsing bug, not "no associations".
                # Logged at ERROR (not swallowed as a normal empty result) because a
                # caller several layers up may otherwise treat this identically to a
                # real "no associations" case with no way to tell them apart.
                logger.error(
                    "get_associations(%s:%s -> %s): HubSpot returned %d result(s) but "
                    "none matched a known id field - sample keys: %s",
                    object_type, object_id, to_object_type, len(raw_results),
                    list(raw_results[0].keys()) if raw_results else [],
                )
            return ids
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(
                f"Failed to get associations from {object_type}:{object_id} "
                f"to {to_object_type}: {str(e)}"
            )

