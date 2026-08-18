"""
Contact operations service for HubSpot.

Handles creating, updating, and finding contacts with proper
field mapping from MemoExtraction to HubSpot properties.
Email is optional. Phone and/or name are enough to create a contact.
Never invent placeholder emails.
"""

from typing import Any, Optional

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
    ) -> dict[str, Any]:
        """
        Convert MemoExtraction fields to HubSpot contact properties.
        
        Args:
            extraction: MemoExtraction from voice memo
            
        Returns:
            Dictionary of HubSpot property names to values
        """
        properties: dict[str, Any] = {}
        
        from .contact_identity import is_real_contact_email

        if is_real_contact_email(extraction.contactEmail):
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
    
    async def get_by_email(self, email: str) -> Optional[HubSpotContact]:
        """
        Get contact by email using HubSpot's idProperty endpoint.
        Fallback when Search API fails (e.g. missing scope) or returns unexpected format.
        """
        if not email or not email.strip():
            return None
        try:
            from urllib.parse import quote
            encoded = quote(email.strip().lower(), safe="")
            response = await self.client.get(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{encoded}",
                params={"idProperty": "email", "properties": "email,firstname,lastname,phone,jobtitle"},
            )
            if response:
                return HubSpotContact(**response)
        except Exception:
            pass
        return None

    async def get(self, contact_id: str, properties: Optional[list[str]] = None) -> HubSpotContact:
        """
        Get a contact by ID.
        """
        props = properties or ["email", "firstname", "lastname", "phone", "jobtitle"]
        try:
            response = await self.client.get(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{contact_id}",
                params={"properties": ",".join(props)},
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotContact(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to get contact: {str(e)}")
    
    async def create(self, properties: dict[str, Any]) -> HubSpotContact:
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
        if not any(properties.get(k) for k in ("email", "phone", "mobilephone", "firstname", "lastname")):
            raise HubSpotError("Need an email, phone, or name to create a contact")

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
        properties: dict[str, Any],
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
        allowed_fields: Optional[list[str]] = None,
    ) -> Optional[HubSpotContact]:
        """
        Create or update a contact from extraction.

        Email is optional. Match by real email, then unique phone.
        Create with phone and/or name when there is no email.
        Never invent a placeholder address.
        """
        from .contact_identity import real_contact_email_or_none
        from .object_properties import contact_properties_from_extraction

        email = real_contact_email_or_none(extraction.contactEmail)
        if not email and extraction.contactEmail:
            extraction = extraction.model_copy(update={"contactEmail": None})
        phone = (extraction.contactPhone or "").strip() or None
        name = (extraction.contactName or "").strip() or None
        if not email and not phone and not name:
            return None

        identity = self.map_extraction_to_properties(extraction)
        properties = contact_properties_from_extraction(
            extraction,
            allowed_fields=allowed_fields,
            identity_props=identity,
        )
        if email:
            properties["email"] = email
        else:
            properties.pop("email", None)

        existing = None
        if email:
            try:
                existing = await self.search.find_contact_by_email(email)
            except Exception:
                existing = await self.get_by_email(email)
        if existing is None and phone:
            try:
                hits = await self.search.find_contacts_by_phone(phone, limit=5)
                if len(hits) == 1:
                    existing = hits[0]
            except Exception:
                existing = None

        if existing:
            update_properties = {
                k: v for k, v in properties.items()
                if v and (k != "email" or not (existing.properties or {}).get("email"))
            }
            if update_properties:
                return await self.update(existing.id, update_properties)
            return existing

        try:
            return await self.create(properties)
        except HubSpotConflictError:
            if email:
                return await self.get_by_email(email)
            return None

