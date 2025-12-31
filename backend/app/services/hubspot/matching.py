"""
Deal matching service for finding existing HubSpot deals.
"""

from typing import Optional
from app.models.memo import MemoExtraction
from app.models.approval import DealMatch
from .client import HubSpotClient
from .exceptions import HubSpotError
from .search import HubSpotSearchService
from .types import Filter, FilterGroup


class HubSpotMatchingService:
    """
    Matches voice memo extractions to existing HubSpot deals.
    
    Matching strategy:
    1. Company name match (highest priority)
    2. Contact email/name match (secondary)
    3. Deal name similarity (fallback)
    
    Returns top matches with confidence scores.
    """
    
    def __init__(
        self,
        client: HubSpotClient,
        search_service: HubSpotSearchService,
    ):
        self.client = client
        self.search = search_service
    
    async def find_matching_deals(
        self,
        extraction: MemoExtraction,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        """
        Find existing deals that match the extraction.
        
        Args:
            extraction: MemoExtraction with company/contact/deal info
            limit: Maximum number of matches to return
            pipeline_id: Optional pipeline ID to filter by
            
        Returns:
            List of DealMatch objects sorted by confidence (highest first)
        """
        matches: list[DealMatch] = []
        
        # Strategy 1: Match by company name (highest confidence)
        if extraction.companyName:
            company_matches = await self._find_by_company(
                extraction.companyName,
                limit=limit,
                pipeline_id=pipeline_id,
            )
            matches.extend(company_matches)
        
        # Strategy 2: Match by contact email/name
        if extraction.contactEmail or extraction.contactName:
            contact_matches = await self._find_by_contact(
                extraction.contactEmail,
                extraction.contactName,
                limit=limit,
                pipeline_id=pipeline_id,
            )
            matches.extend(contact_matches)
        
        # Strategy 3: Match by deal name similarity (if we have a deal name)
        # This is less reliable, so lower confidence
        if extraction.companyName:
            deal_name = f"{extraction.companyName} Deal"
            name_matches = await self._find_by_deal_name(
                deal_name,
                limit=limit,
                pipeline_id=pipeline_id,
            )
            matches.extend(name_matches)
        
        # Deduplicate by deal_id and sort by confidence
        seen_ids = set()
        unique_matches = []
        
        for match in sorted(matches, key=lambda m: m.match_confidence, reverse=True):
            if match.deal_id not in seen_ids:
                seen_ids.add(match.deal_id)
                unique_matches.append(match)
                
                if len(unique_matches) >= limit:
                    break
        
        return unique_matches
    
    async def _find_by_company(
        self,
        company_name: str,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        """Find deals associated with a company"""
        try:
            # First, find the company
            company = await self.search.find_company_by_name(company_name)
            
            if not company:
                return []
            
            # Then find deals associated with this company
            # Note: HubSpot search doesn't directly support association filters
            # We'll search deals and filter by association in a follow-up call
            # For MVP, we'll use a simpler approach: search deals by name
            
            # Search deals with company name in deal name
            filters = [
                Filter(
                    propertyName="dealname",
                    operator="CONTAINS_TOKEN",
                    value=company_name,
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
            
            deals = await self.search.search(
                "deals",
                filters,
                properties=["dealname", "amount", "dealstage", "closedate", "hs_lastmodifieddate"],
                limit=limit,
            )
            
            matches = []
            for deal_data in deals:
                # Get associated company to verify match
                deal_id = deal_data.get("id")
                if not deal_id:
                    continue
                
                # Calculate confidence based on name match
                deal_name = deal_data.get("properties", {}).get("dealname", "")
                confidence = 0.7 if company_name.lower() in deal_name.lower() else 0.5
                
                matches.append(DealMatch(
                    deal_id=deal_id,
                    deal_name=deal_name,
                    company_name=company_name,
                    amount=deal_data.get("properties", {}).get("amount"),
                    stage=deal_data.get("properties", {}).get("dealstage"),
                    last_updated=deal_data.get("properties", {}).get("hs_lastmodifieddate", ""),
                    match_confidence=confidence,
                    match_reason=f"Company name match: {company_name}",
                ))
            
            return matches
            
        except Exception as e:
            # Return empty list on error (don't fail the whole flow)
            return []
    
    async def _find_by_contact(
        self,
        contact_email: Optional[str],
        contact_name: Optional[str],
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        """Find deals associated with a contact"""
        try:
            contact = None
            
            # Find contact by email first (more reliable)
            if contact_email:
                contact = await self.search.find_contact_by_email(contact_email)
            
            # Fallback to name search
            if not contact and contact_name:
                contact = await self.search.find_contact_by_name(contact_name)
            
            if not contact:
                return []
            
            # Search deals with contact name in deal name
            search_term = contact_name or contact_email or ""
            if not search_term:
                return []
            
            filters = [
                Filter(
                    propertyName="dealname",
                    operator="CONTAINS_TOKEN",
                    value=search_term,
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
            
            deals = await self.search.search(
                "deals",
                filters,
                properties=["dealname", "amount", "dealstage", "closedate", "hs_lastmodifieddate"],
                limit=limit,
            )
            
            matches = []
            for deal_data in deals:
                deal_id = deal_data.get("id")
                if not deal_id:
                    continue
                
                deal_name = deal_data.get("properties", {}).get("dealname", "")
                confidence = 0.6 if contact_email else 0.5
                
                matches.append(DealMatch(
                    deal_id=deal_id,
                    deal_name=deal_name,
                    contact_name=contact_name,
                    amount=deal_data.get("properties", {}).get("amount"),
                    stage=deal_data.get("properties", {}).get("dealstage"),
                    last_updated=deal_data.get("properties", {}).get("hs_lastmodifieddate", ""),
                    match_confidence=confidence,
                    match_reason=f"Contact match: {contact_name or contact_email}",
                ))
            
            return matches
            
        except Exception:
            return []
    
    async def _find_by_deal_name(
        self,
        deal_name: str,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        """Find deals by name similarity"""
        try:
            filters = [
                Filter(
                    propertyName="dealname",
                    operator="CONTAINS_TOKEN",
                    value=deal_name,
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
            
            deals = await self.search.search(
                "deals",
                filters,
                properties=["dealname", "amount", "dealstage", "closedate", "hs_lastmodifieddate"],
                limit=limit,
            )
            
            matches = []
            for deal_data in deals:
                deal_id = deal_data.get("id")
                if not deal_id:
                    continue
                
                found_name = deal_data.get("properties", {}).get("dealname", "")
                # Lower confidence for name-only matches
                confidence = 0.4
                
                matches.append(DealMatch(
                    deal_id=deal_id,
                    deal_name=found_name,
                    amount=deal_data.get("properties", {}).get("amount"),
                    stage=deal_data.get("properties", {}).get("dealstage"),
                    last_updated=deal_data.get("properties", {}).get("hs_lastmodifieddate", ""),
                    match_confidence=confidence,
                    match_reason=f"Deal name similarity: {found_name}",
                ))
            
            return matches
            
        except Exception:
            return []

