"""
Deal matching service for finding existing HubSpot deals.
"""

import logging
from typing import Optional
from app.models.memo import MemoExtraction
from app.models.approval import DealMatch
from .client import HubSpotClient
from .exceptions import HubSpotError
from .search import HubSpotSearchService
from .associations import HubSpotAssociationService
from .types import Filter, FilterGroup

logger = logging.getLogger(__name__)


class HubSpotMatchingService:
    """
    Matches voice memo extractions to existing HubSpot deals.
    
    Matching strategy:
    1. Company association (highest): find company by name → get deals linked to that company
    2. Deal name contains company (e.g. "Nacho Company" matches "Nacho Company Deal")
    3. Contact email/name match (secondary)
    4. Deal name similarity (fallback)
    
    Returns top matches with confidence scores.
    """
    
    def __init__(
        self,
        client: HubSpotClient,
        search_service: HubSpotSearchService,
        associations_service: Optional[HubSpotAssociationService] = None,
    ):
        self.client = client
        self.search = search_service
        self.associations = associations_service or HubSpotAssociationService(client)
    
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
        
        # Strategy 1 (highest): Match by company association - company → deals
        if extraction.companyName:
            assoc_matches = await self._find_by_company_association(
                extraction.companyName,
                limit=limit,
                pipeline_id=pipeline_id,
            )
            matches.extend(assoc_matches)
        
        # Strategy 2: Match by deal name containing company
        if extraction.companyName:
            company_matches = await self._find_by_company(
                extraction.companyName,
                limit=limit,
                pipeline_id=pipeline_id,
            )
            matches.extend(company_matches)
        
        # Strategy 3: Match by contact email/name
        if extraction.contactEmail or extraction.contactName:
            contact_matches = await self._find_by_contact(
                extraction.contactEmail,
                extraction.contactName,
                limit=limit,
                pipeline_id=pipeline_id,
            )
            matches.extend(contact_matches)
        
        # If pipeline filter excluded all matches, retry without pipeline
        if not matches and pipeline_id and extraction.companyName:
            logger.info("No matches with pipeline %s, retrying without pipeline filter", pipeline_id)
            fallback = await self._find_by_company_association(
                extraction.companyName, limit=limit, pipeline_id=None
            )
            fallback.extend(
                await self._find_by_company(
                    extraction.companyName, limit=limit, pipeline_id=None
                )
            )
            matches.extend(fallback)
        
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
    
    def _company_search_terms(self, company_name: str) -> list[str]:
        """Generate search terms for company name - try full name, then first/last word."""
        s = company_name.strip()
        if not s:
            return []
        terms = [s]
        parts = s.split()
        if len(parts) > 1:
            terms.append(parts[0])
            if len(parts) > 2:
                terms.append(parts[-1])
        return terms[:3]

    async def _find_by_company_association(
        self,
        company_name: str,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        """
        Find deals by company association: search companies by name, then get deals
        linked to those companies. Most reliable when deals are associated with companies.
        Tries multiple search terms (full name, first word) for better match.
        """
        try:
            companies = []
            for term in self._company_search_terms(company_name):
                companies = await self.search.search(
                    "companies",
                    [Filter(propertyName="name", operator="CONTAINS_TOKEN", value=term)],
                    properties=["name"],
                    limit=5,
                )
                if companies:
                    break
            logger.info("Match: company search %r -> %d companies", company_name, len(companies or []))
            if not companies:
                return []
            
            all_deal_ids: list[str] = []
            for comp in companies:
                comp_id = comp.get("id")
                if not comp_id:
                    continue
                # HubSpot v4 uses plural: companies, deals
                ids = await self.associations.get_associations(
                    "companies", str(comp_id), "deals"
                )
                logger.info("Match: company %s -> %d deal associations: %s", comp_id, len(ids), ids[:5])
                all_deal_ids.extend(ids)
            
            if not all_deal_ids:
                logger.info("Match: no deal associations for company %r", company_name)
                return []
            
            # Fetch deal details (batch read)
            deal_ids = all_deal_ids[:limit * 2]  # fetch a few extra for pipeline filter
            props = ["dealname", "amount", "dealstage", "closedate", "hs_lastmodifieddate", "pipeline"]
            
            batch_url = "/crm/v3/objects/deals/batch/read"
            batch_body = {
                "inputs": [{"id": did} for did in deal_ids],
                "properties": props,
            }
            response = await self.client.post(batch_url, data=batch_body)
            
            if not response or "results" not in response:
                return []
            
            matches = []
            for deal_data in response.get("results", []):
                deal_id = deal_data.get("id")
                if not deal_id:
                    continue
                if pipeline_id:
                    deal_pipeline = deal_data.get("properties", {}).get("pipeline")
                    if deal_pipeline and deal_pipeline != pipeline_id:
                        continue
                deal_name = deal_data.get("properties", {}).get("dealname", "")
                matches.append(DealMatch(
                    deal_id=deal_id,
                    deal_name=deal_name,
                    company_name=company_name,
                    amount=deal_data.get("properties", {}).get("amount"),
                    stage=deal_data.get("properties", {}).get("dealstage"),
                    last_updated=deal_data.get("properties", {}).get("hs_lastmodifieddate", ""),
                    match_confidence=0.95,
                    match_reason=f"Company association: {company_name}",
                ))
                if len(matches) >= limit:
                    break
            
            return matches
            
        except Exception as e:
            logger.warning("Company association matching failed for %s: %s", company_name, e)
            return []
    
    async def _find_by_company(
        self,
        company_name: str,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        """Find deals by deal name containing company (e.g. 'Nacho Company' matches 'Nacho Company Deal')"""
        try:
            # Try exact deal name first: "{company} Deal" (our convention)
            exact_deal_name = f"{company_name.strip()} Deal"
            filters_eq = [
                Filter(propertyName="dealname", operator="EQ", value=exact_deal_name),
            ]
            if pipeline_id:
                filters_eq.append(
                    Filter(propertyName="pipeline", operator="EQ", value=pipeline_id)
                )
            deals = await self.search.search(
                "deals",
                filters_eq,
                properties=["dealname", "amount", "dealstage", "closedate", "hs_lastmodifieddate"],
                limit=limit,
            )
            logger.info("Match: deal EQ %r -> %d deals", exact_deal_name, len(deals or []))
            if deals:
                matches = []
                for deal_data in deals:
                    deal_id = deal_data.get("id")
                    if not deal_id:
                        continue
                    deal_name = deal_data.get("properties", {}).get("dealname", "")
                    matches.append(DealMatch(
                        deal_id=deal_id,
                        deal_name=deal_name,
                        company_name=company_name,
                        amount=deal_data.get("properties", {}).get("amount"),
                        stage=deal_data.get("properties", {}).get("dealstage"),
                        last_updated=deal_data.get("properties", {}).get("hs_lastmodifieddate", ""),
                        match_confidence=0.85,
                        match_reason=f"Deal name match: {exact_deal_name}",
                    ))
                return matches
            
            # Fallback: CONTAINS_TOKEN - try full name, then first/last word
            deals = []
            for term in self._company_search_terms(company_name):
                filters = [
                    Filter(
                        propertyName="dealname",
                        operator="CONTAINS_TOKEN",
                        value=term,
                    )
                ]
                if pipeline_id:
                    filters.append(
                        Filter(propertyName="pipeline", operator="EQ", value=pipeline_id)
                    )
                deals = await self.search.search(
                    "deals",
                    filters,
                    properties=["dealname", "amount", "dealstage", "closedate", "hs_lastmodifieddate"],
                    limit=limit,
                )
                if deals:
                    break
            # Post-filter: verify company name actually appears in deal name (avoids false positives from generic tokens like "Deal")
            company_lower = company_name.strip().lower()
            deals = [d for d in (deals or []) if company_lower in d.get("properties", {}).get("dealname", "").lower()]
            matches = []
            for deal_data in (deals or []):
                deal_id = deal_data.get("id")
                if not deal_id:
                    continue
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
                    match_reason=f"Company name in deal: {company_name}",
                ))
            return matches
            
        except Exception as e:
            logger.warning("Deal name search failed for company %s: %s", company_name, e)
            return []
    
    async def _find_by_contact(
        self,
        contact_email: Optional[str],
        contact_name: Optional[str],
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        """Find deals by contact name or email (searches deal name)"""
        try:
            search_term = (contact_name or contact_email or "").strip()
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

