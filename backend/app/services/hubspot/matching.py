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

# Deals asked for per name search, in every pipeline: the pipeline filter is applied to these.
_DEAL_NAME_SEARCH_LIMIT = 20


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
        self._company_deals: dict[tuple[str, int], list[dict]] = {}
        self._deal_searches: dict[tuple[str, str], list[dict]] = {}
    
    async def find_matching_deals(
        self,
        extraction: MemoExtraction,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
        known_anchor=None,
    ) -> list[DealMatch]:
        """
        Find existing deals that match the extraction.

        Contact-first: when a real email resolves to a HubSpot contact, prefer
        deals associated to that contact. Then fall back to company/deal-name strategies.
        `known_anchor` is the contact the caller already locked: it is used as is, not
        looked up again from the extraction.
        """
        matches: list[DealMatch] = []

        # Strategy 0 (highest): deals linked to email-matched contact
        anchor = known_anchor or await self.resolve_contact_anchor(
            extraction, limit_deals=limit, pipeline_id=pipeline_id
        )
        if anchor and anchor.deal_matches:
            matches.extend(anchor.deal_matches)

        # Strategy 1: Match by company association - company → deals
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

        # Strategy 3: Weak dealname contains contact — only when no contact lock
        if not anchor and (extraction.contactEmail or extraction.contactName or extraction.contactPhone):
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

    async def resolve_contact_anchor(
        self,
        extraction: MemoExtraction,
        limit_deals: int = 5,
        pipeline_id: Optional[str] = None,
        preferred_contact_id: Optional[str] = None,
    ):
        """Resolve contact identity and return linked deals/companies when locked."""
        from .contact_identity import resolve_contact_anchor
        from .contacts import HubSpotContactService

        return await resolve_contact_anchor(
            extraction=extraction,
            search=self.search,
            associations=self.associations,
            contacts=HubSpotContactService(self.client, self.search),
            limit_deals=limit_deals,
            pipeline_id=pipeline_id,
            preferred_contact_id=preferred_contact_id,
        )

    async def resolve_identity(
        self,
        extraction: MemoExtraction,
        limit_deals: int = 5,
        pipeline_id: Optional[str] = None,
        preferred_contact_id: Optional[str] = None,
    ):
        """Full identity cascade including ambiguous candidates."""
        from .contact_identity import resolve_identity
        from .contacts import HubSpotContactService

        return await resolve_identity(
            extraction=extraction,
            search=self.search,
            associations=self.associations,
            contacts=HubSpotContactService(self.client, self.search),
            limit_deals=limit_deals,
            pipeline_id=pipeline_id,
            preferred_contact_id=preferred_contact_id,
        )
    
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

    async def _read_company_deals(self, company_name: str, limit: int) -> list[dict]:
        """The deals linked to the companies named like `company_name`, as HubSpot returns them."""
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
            ids = await self.associations.get_associations("companies", str(comp_id), "deals")
            logger.info("Match: company %s -> %d deal associations: %s", comp_id, len(ids), ids[:5])
            all_deal_ids.extend(ids)

        if not all_deal_ids:
            logger.info("Match: no deal associations for company %r", company_name)
            return []

        # Fetch deal details (batch read); a few extra for the pipeline filter
        response = await self.client.post(
            "/crm/v3/objects/deals/batch/read",
            data={
                "inputs": [{"id": did} for did in all_deal_ids[: limit * 2]],
                "properties": ["dealname", "amount", "dealstage", "closedate", "hs_lastmodifieddate", "pipeline"],
            },
        )
        if not response or "results" not in response:
            return []
        return list(response.get("results", []))

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
            # The same company's deals, read once: the retry without a pipeline filter reuses them.
            key = (company_name, limit)
            if key not in self._company_deals:
                self._company_deals[key] = await self._read_company_deals(company_name, limit)
            matches = []
            for deal_data in self._company_deals[key]:
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
    
    async def _search_deals_by_name(self, operator: str, value: str) -> list[dict]:
        """Deals whose name matches, in every pipeline; read once per call, the pipeline is chosen after.

        The search with the pipeline filter and the retry without it used to ask HubSpot the
        same question twice (7 searches in a row and a 429 on 2026-11-17)."""
        key = (operator, value)
        if key not in self._deal_searches:
            self._deal_searches[key] = await self.search.search(
                "deals",
                [Filter(propertyName="dealname", operator=operator, value=value)],
                properties=["dealname", "amount", "dealstage", "closedate", "hs_lastmodifieddate", "pipeline"],
                limit=_DEAL_NAME_SEARCH_LIMIT,
            ) or []
        return self._deal_searches[key]

    async def _find_by_company(
        self,
        company_name: str,
        limit: int = 3,
        pipeline_id: Optional[str] = None,
    ) -> list[DealMatch]:
        """Find deals by deal name containing company (e.g. 'Nacho Company' matches 'Nacho Company Deal')"""

        def in_pipeline(deals: list[dict]) -> list[dict]:
            if not pipeline_id:
                return list(deals)
            return [d for d in deals if (d.get("properties") or {}).get("pipeline") == pipeline_id]

        try:
            # Try exact deal name first: "{company} Deal" (our convention)
            exact_deal_name = f"{company_name.strip()} Deal"
            deals = in_pipeline(await self._search_deals_by_name("EQ", exact_deal_name))[:limit]
            logger.info("Match: deal EQ %r -> %d deals", exact_deal_name, len(deals))
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
                deals = in_pipeline(await self._search_deals_by_name("CONTAINS_TOKEN", term))[:limit]
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

