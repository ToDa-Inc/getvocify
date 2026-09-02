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


def phone_digits_match(a: Optional[str], b: Optional[str]) -> bool:
    """True when two CRM/Twilio numbers are the same phone in different formats."""
    da = normalize_phone_digits(a)
    db = normalize_phone_digits(b)
    if len(da) < 6 or len(db) < 6:
        return False
    n = 9 if min(len(da), len(db)) >= 9 else min(len(da), len(db))
    return da[-n:] == db[-n:]


def phone_search_variants(
    phone: Optional[str],
    default_country_code: str = "34",
) -> list[str]:
    """Formats HubSpot actually stores: E.164, national, 00, trunk-0, spaced."""
    digits = normalize_phone_digits(phone)
    if len(digits) < 7:
        return []
    cc = (default_country_code or "34").lstrip("+")
    if digits.startswith(cc) and len(digits) - len(cc) >= 7:
        national = digits[len(cc) :].lstrip("0")
        full = digits
    else:
        national = digits.lstrip("0")
        full = f"{cc}{national}"
    variants = [
        f"+{full}",
        full,
        f"00{full}",
        national,
        f"0{national}",
        f"+{cc} {national}",
        f"{cc} {national}",
    ]
    if len(national) == 9:
        a, b, c, d = national[:3], national[3:5], national[5:7], national[7:]
        variants.extend(
            [
                f"+{cc} {a} {b} {c} {d}",
                f"{a} {b} {c} {d}",
                f"+{cc} {national[:3]} {national[3:6]} {national[6:]}",
                f"{national[:3]} {national[3:6]} {national[6:]}",
                f"{national[:3]}-{national[3:6]}-{national[6:]}",
            ]
        )
    if len(national) == 10:
        variants.extend(
            [
                f"({national[:3]}) {national[3:6]}-{national[6:]}",
                f"{national[:3]}-{national[3:6]}-{national[6:]}",
                f"+{cc} {national[:3]} {national[3:6]} {national[6:]}",
            ]
        )
    seen: set[str] = set()
    out: list[str] = []
    for value in variants:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def choose_dialed_contact(hits: list[HubSpotContact], phone: str) -> Optional[HubSpotContact]:
    """Pick the HubSpot contact for a number we just dialed.

    Unique exact match wins. Several contacts sharing the number: prefer a
    real person (named, mobilephone) over a placeholder. Tied ranks stay unset.
    """
    exact: list[HubSpotContact] = []
    for hit in hits:
        props = getattr(hit, "properties", None) or {}
        if not isinstance(props, dict):
            continue
        if phone_digits_match(phone, props.get("phone")) or phone_digits_match(
            phone, props.get("mobilephone")
        ):
            exact.append(hit)
    if not exact:
        return hits[0] if len(hits) == 1 else None
    if len(exact) == 1:
        return exact[0]

    def score(hit: HubSpotContact) -> int:
        props = hit.properties or {}
        first = (props.get("firstname") or "").strip().lower()
        last = (props.get("lastname") or "").strip()
        points = 0
        if first and first != "contact":
            points += 3
        if last:
            points += 1
        if phone_digits_match(phone, props.get("mobilephone")):
            points += 2
        return points

    ranked = sorted(exact, key=score, reverse=True)
    if score(ranked[0]) > score(ranked[1]):
        return ranked[0]
    return None


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
        default_country_code: str = "34",
    ) -> list[HubSpotContact]:
        """Find contacts by phone / mobilephone across common stored formats."""
        digits = normalize_phone_digits(phone)
        if len(digits) < 7:
            return []
        needle = digits[-9:] if len(digits) >= 9 else digits
        variants = phone_search_variants(phone, default_country_code)
        e164 = next((v for v in variants if v.startswith("+") and " " not in v), None)
        cc = (default_country_code or "34").lstrip("+")
        if digits.startswith(cc) and len(digits) - len(cc) >= 7:
            national = digits[len(cc) :].lstrip("0")
        else:
            national = digits.lstrip("0")
        eq_values = [v for v in (e164, national) if v]
        props = [
            "email",
            "firstname",
            "lastname",
            "phone",
            "mobilephone",
            "jobtitle",
            "hs_searchable_calculated_phone_number",
            "hs_searchable_calculated_mobile_number",
        ]
        searches: list[list[Filter]] = []
        for prop in ("phone", "mobilephone"):
            searches.append(
                [Filter(propertyName=prop, operator="CONTAINS_TOKEN", value=needle)]
            )
            for value in eq_values:
                searches.append(
                    [Filter(propertyName=prop, operator="EQ", value=value)]
                )
        last6 = needle[-6:] if len(needle) >= 6 else needle
        for prop in (
            "hs_searchable_calculated_phone_number",
            "hs_searchable_calculated_mobile_number",
        ):
            searches.append([Filter(propertyName=prop, operator="EQ", value=last6)])

        seen: set[str] = set()
        out: list[HubSpotContact] = []
        for filters in searches:
            try:
                rows = await self.search(
                    self.CONTACTS,
                    filters,
                    properties=props,
                    limit=limit,
                )
            except Exception:
                continue
            for row in rows or []:
                rid = str(row.get("id") or "")
                if not rid or rid in seen:
                    continue
                row_props = row.get("properties") or {}
                stored_values = (
                    row_props.get("phone"),
                    row_props.get("mobilephone"),
                    row_props.get("hs_searchable_calculated_phone_number"),
                    row_props.get("hs_searchable_calculated_mobile_number"),
                )
                if not any(phone_digits_match(phone, stored) for stored in stored_values):
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

    async def search_contacts_by_query(
        self,
        query: str,
        limit: int = 10,
    ) -> list[HubSpotContact]:
        """Manual contact picker: email, phone, then HubSpot text query (prefix-safe)."""
        q = (query or "").strip()
        if not q:
            return []
        if "@" in q:
            found = await self.find_contact_by_email(q)
            return [found] if found else []
        digits = normalize_phone_digits(q)
        if len(digits) >= 7:
            phone_hits = await self.find_contacts_by_phone(q, limit=limit)
            if phone_hits:
                return phone_hits
        request = SearchRequest(
            query=q,
            properties=["email", "firstname", "lastname", "phone", "mobilephone", "jobtitle"],
            limit=limit,
        )
        try:
            response = await self.client.post(
                f"/crm/v3/objects/{self.CONTACTS}/search",
                data=request.model_dump(exclude_none=True, by_alias=True),
            )
        except Exception:
            return []
        out: list[HubSpotContact] = []
        for row in (response or {}).get("results") or []:
            try:
                out.append(HubSpotContact(**row))
            except Exception:
                continue
        return out

