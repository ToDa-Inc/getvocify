"""
Contact operations service for HubSpot.

Handles creating, updating, and finding contacts with proper
field mapping from MemoExtraction to HubSpot properties.
"""

from .client import HubSpotClient
from .exceptions import HubSpotError, HubSpotConflictError
from .types import HubSpotContact, CreateObjectRequest, UpdateObjectRequest
from .search import HubSpotSearchService
from app.models.memo import MemoExtraction


class HubSpotContactService:
    """
    Service for managing HubSpot contacts.
    
    Features:
    - Field mapping from MemoExtraction to HubSpot properties
    - Name parsing (full name → firstname/lastname)
    - Deduplication by email
    - Create or update logic
    """
    
    OBJECT_TYPE = "contacts"
    
    def __init__(self, client: HubSpotClient, search: HubSpotSearchService):
        self.client = client
        self.search = search
    
    def _parse_name(self, full_name: str) -> tuple[str, str]:
        """
        Parse full name into first and last name.
        
        Args:
            full_name: Full name (e.g., "John Smith" or "John")
            
        Returns:
            Tuple of (firstname, lastname)
        """
        if not full_name or not full_name.strip():
            return ("", "")
        
        parts = full_name.strip().split(None, 1)
        firstname = parts[0] if parts else ""
        lastname = parts[1] if len(parts) > 1 else ""
        
        return (firstname, lastname)
    
    def map_extraction_to_properties(
        self,
        extraction: MemoExtraction,
    ) -> dict[str, any]:
        """
        Convert MemoExtraction fields to HubSpot contact properties.
        
        Args:
            extraction: MemoExtraction from voice memo
            
        Returns:
            Dictionary of HubSpot property names to values
        """
        properties: dict[str, any] = {}
        
        # Email (unique identifier, required for contacts)
        if extraction.contactEmail:
            properties["email"] = extraction.contactEmail.strip().lower()
        
        # Name parsing
        if extraction.contactName:
            firstname, lastname = self._parse_name(extraction.contactName)
            if firstname:
                properties["firstname"] = firstname
            if lastname:
                properties["lastname"] = lastname
        
        # Phone
        if extraction.contactPhone:
            properties["phone"] = extraction.contactPhone.strip()
        
        # Job title / role
        if extraction.contactRole:
            properties["jobtitle"] = extraction.contactRole.strip()
        
        return properties
    
    async def get(self, contact_id: str) -> HubSpotContact:
        """
        Get a contact by ID.
        
        Args:
            contact_id: HubSpot contact ID
            
        Returns:
            HubSpotContact object
            
        Raises:
            HubSpotNotFoundError if contact doesn't exist
            HubSpotError for other errors
        """
        try:
            response = await self.client.get(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{contact_id}",
                params={"properties": "email,firstname,lastname,phone,jobtitle"},
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotContact(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to get contact: {str(e)}")
    
    async def create(self, properties: dict[str, any]) -> HubSpotContact:
        """
        Create a new contact.
        
        Args:
            properties: Dictionary of HubSpot property names to values
            
        Returns:
            Created HubSpotContact
            
        Raises:
            HubSpotConflictError if email already exists
            HubSpotError for other errors
        """
        if not properties.get("email"):
            raise HubSpotError("Email is required to create a contact")
        
        request = CreateObjectRequest(properties=properties)
        
        try:
            response = await self.client.post(
                f"/crm/v3/objects/{self.OBJECT_TYPE}",
                data=request.model_dump(exclude_none=True, by_alias=True),
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotContact(**response)
            
        except HubSpotConflictError:
            # Email already exists - this is expected in some cases
            raise
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to create contact: {str(e)}")
    
    async def update(
        self,
        contact_id: str,
        properties: dict[str, any],
    ) -> HubSpotContact:
        """
        Update an existing contact.
        
        Args:
            contact_id: HubSpot contact ID
            properties: Dictionary of properties to update
            
        Returns:
            Updated HubSpotContact
            
        Raises:
            HubSpotNotFoundError if contact doesn't exist
            HubSpotError for other errors
        """
        request = UpdateObjectRequest(properties=properties)
        
        try:
            response = await self.client.patch(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{contact_id}",
                data=request.model_dump(exclude_none=True, by_alias=True),
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotContact(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to update contact: {str(e)}")
    
    async def create_or_update(
        self,
        extraction: MemoExtraction,
    ) -> HubSpotContact | None:
        """
        Create or update a contact based on extraction data.
        
        Logic:
        1. If email exists, find existing contact
        2. If found, update it with new data
        3. If not found, create new contact
        4. If no email, return None (can't create contact without email)
        
        Args:
            extraction: MemoExtraction with contact data
            
        Returns:
            HubSpotContact if created/updated, None if no email provided
            
        Raises:
            HubSpotError for API errors
        """
        # Can't create contact without email
        if not extraction.contactEmail:
            return None
        
        properties = self.map_extraction_to_properties(extraction)
        
        # Try to find existing contact by email
        existing = await self.search.find_contact_by_email(extraction.contactEmail)
        
        if existing:
            # Update existing contact
            # Only update fields that have values (don't overwrite with empty)
            update_properties = {
                k: v for k, v in properties.items()
                if v and k != "email"  # Don't update email
            }
            
            if update_properties:
                return await self.update(existing.id, update_properties)
            return existing
        else:
            # Create new contact
            return await self.create(properties)

