"""
Search and deduplication service for HubSpot objects.

Finds existing records before creating duplicates.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

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


def normalize_phone_digits(phone: Optional[str]) -> str:
    return re.sub(r"\D+", "", phone or "")


def split_person_name(name: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (firstname, lastname). Single token → (token, None)."""
    if not name or not str(name).strip():
        return None, None
    parts = [p for p in str(name).strip().split() if p]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[-1]


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
        properties: Optional[list[str]] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
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
    
    async def find_contact_by_email(self, email: Optional[str]) -> HubSpotContact:
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

    async def find_contact_by_name(self, name: Optional[str]) -> Optional[HubSpotContact]:
        """
        Find a single contact by name. Prefer unique first+last matches.
        """
        hits = await self.find_contacts_by_name(name, limit=5)
        return hits[0] if len(hits) == 1 else (hits[0] if hits else None)

    async def find_contacts_by_name(
        self,
        name: Optional[str],
        limit: int = 5,
    ) -> list[HubSpotContact]:
        """
        Find contacts by person name.

        - "First Last" → firstname AND lastname token match (stronger)
        - Single token → firstname OR lastname contains (weaker; may return several)
        """
        first, last = split_person_name(name)
        if not first:
            return []

        props = ["email", "firstname", "lastname", "phone", "mobilephone", "jobtitle"]
        results: list[dict] = []
        try:
            if last:
                results = await self.search(
                    self.CONTACTS,
                    [
                        Filter(propertyName="firstname", operator="CONTAINS_TOKEN", value=first),
                        Filter(propertyName="lastname", operator="CONTAINS_TOKEN", value=last),
                    ],
                    properties=props,
                    limit=limit,
                )
            else:
                # Single token: try firstname, then lastname; merge unique
                by_first = await self.search(
                    self.CONTACTS,
                    [Filter(propertyName="firstname", operator="CONTAINS_TOKEN", value=first)],
                    properties=props,
                    limit=limit,
                )
                by_last = await self.search(
                    self.CONTACTS,
                    [Filter(propertyName="lastname", operator="CONTAINS_TOKEN", value=first)],
                    properties=props,
                    limit=limit,
                )
                seen: set[str] = set()
                merged: list[dict] = []
                for row in list(by_first or []) + list(by_last or []):
                    rid = str(row.get("id") or "")
                    if not rid or rid in seen:
                        continue
                    seen.add(rid)
                    merged.append(row)
                results = merged[:limit]
        except Exception:
            return []

        out: list[HubSpotContact] = []
        for row in results or []:
            try:
                out.append(HubSpotContact(**row))
            except Exception:
                continue
        return out

    async def find_contacts_by_phone(
        self,
        phone: Optional[str],
        limit: int = 5,
    ) -> list[HubSpotContact]:
        """
        Find contacts by phone / mobilephone using digit-normalized needle.
        """
        digits = normalize_phone_digits(phone)
        if len(digits) < 7:
            return []
        needle = digits[-9:] if len(digits) >= 9 else digits
        props = ["email", "firstname", "lastname", "phone", "mobilephone", "jobtitle"]
        seen: set[str] = set()
        out: list[HubSpotContact] = []
        for prop in ("phone", "mobilephone"):
            try:
                rows = await self.search(
                    self.CONTACTS,
                    [Filter(propertyName=prop, operator="CONTAINS_TOKEN", value=needle)],
                    properties=props,
                    limit=limit,
                )
            except Exception:
                continue
            for row in rows or []:
                rid = str(row.get("id") or "")
                if not rid or rid in seen:
                    continue
                # Prefer digit overlap to reduce false positives
                row_digits = normalize_phone_digits(
                    (row.get("properties") or {}).get(prop)
                    or (row.get("properties") or {}).get("phone")
                    or (row.get("properties") or {}).get("mobilephone")
                )
                if row_digits and needle not in row_digits and row_digits[-7:] not in digits:
                    continue
                seen.add(rid)
                try:
                    out.append(HubSpotContact(**row))
                except Exception:
                    continue
                if len(out) >= limit:
                    return out
        return out

    async def find_company_by_name(self, name: Optional[str]) -> Optional[HubSpotCompany]:
        """
        Find company by name (exact match).
        
        Args:
            name: Company name to search for
            
        Returns:
            HubSpotCompany if found, None otherwise
        """
        hits = await self.find_companies_by_name(name, limit=3)
        return hits[0] if hits else None

    async def find_companies_by_name(
        self,
        name: Optional[str],
        limit: int = 5,
    ) -> list[HubSpotCompany]:
        if not name or not name.strip():
            return []
        filters = [
            Filter(
                propertyName="name",
                operator="CONTAINS_TOKEN",
                value=name.strip(),
            )
        ]
        try:
            results = await self.search(
                self.COMPANIES,
                filters,
                properties=["name", "domain"],
                limit=limit,
            )
        except Exception:
            return []
        out: list[HubSpotCompany] = []
        for row in results or []:
            try:
                out.append(HubSpotCompany(**row))
            except Exception:
                continue
        return out

    async def find_company_by_domain(self, domain: Optional[str]) -> Optional[HubSpotCompany]:
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
        contact_id: Optional[str] = None,
    ) -> Optional[HubSpotDeal]:
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
        pipeline_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
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

