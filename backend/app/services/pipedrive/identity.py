"""Contact-first identity. Same cascade + DTOs as HubSpot contact_identity."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.models.approval import ContactMatch, DealMatch
from app.models.memo import MemoExtraction
from app.services.hubspot.contact_identity import (
    ContactAnchor,
    IdentityResolution,
    is_real_contact_email,
    real_contact_email_or_none,
)

from .search import PipedriveSearchService, primary_email, primary_phone

logger = logging.getLogger(__name__)


def _org_id(record: dict[str, Any]) -> Optional[str]:
    oid = record.get("org_id")
    if isinstance(oid, dict):
        oid = oid.get("value") or oid.get("id")
    return str(oid) if oid is not None else None


def _org_name(record: dict[str, Any]) -> Optional[str]:
    org = record.get("org_id")
    if isinstance(org, dict):
        return org.get("name") or None
    return record.get("org_name") or None


def _person_name(person: dict[str, Any]) -> Optional[str]:
    return (person.get("name") or "").strip() or None


def _to_contact_match(
    person: dict[str, Any],
    *,
    reason: str,
    confidence: float,
    company_id: Optional[str] = None,
    company_name: Optional[str] = None,
) -> ContactMatch:
    return ContactMatch(
        contact_id=str(person.get("id")),
        email=primary_email(person) or "",
        name=_person_name(person),
        phone=primary_phone(person),
        company_id=company_id or _org_id(person),
        company_name=company_name or _org_name(person),
        match_confidence=confidence,
        match_reason=reason,
    )


async def _deals_for_person(search: PipedriveSearchService, person: dict[str, Any], *, limit: int) -> list[DealMatch]:
    pid = person.get("id")
    if pid is None:
        return []
    try:
        rows = await search.deals_for_person(str(pid), limit=limit)
    except Exception as e:
        logger.warning("Pipedrive person→deals failed: %s", e)
        return []
    out: list[DealMatch] = []
    for row in rows:
        did = row.get("id")
        if did is None:
            continue
        out.append(
            DealMatch(
                deal_id=str(did),
                deal_name=row.get("title") or "Deal",
                company_name=_org_name(row) or _org_name(person),
                contact_name=_person_name(person),
                contact_email=primary_email(person) or None,
                amount=str(row["value"]) if row.get("value") is not None else None,
                stage=str(row.get("stage_id")) if row.get("stage_id") is not None else None,
                last_updated=str(row.get("update_time") or row.get("updated_at") or ""),
                match_confidence=0.95,
                match_reason="Linked to matched contact",
            )
        )
    return out[:limit]


async def _anchor(
    person: dict[str, Any],
    search: PipedriveSearchService,
    *,
    reason: str,
    confidence: float,
    limit_deals: int,
) -> ContactAnchor:
    company_id = _org_id(person)
    company_name = _org_name(person)
    if company_id and not company_name:
        try:
            org = await search.get_organization(company_id)
            company_name = org.get("name")
        except Exception:
            pass
    deals = await _deals_for_person(search, person, limit=limit_deals)
    email = primary_email(person)
    return ContactAnchor(
        contact_id=str(person["id"]),
        email=email or "",
        name=_person_name(person),
        phone=primary_phone(person),
        company_id=company_id,
        company_name=company_name,
        deal_matches=deals,
        match_reason=reason,
        match_confidence=confidence,
    )


class PipedriveIdentityService:
    def __init__(self, search: PipedriveSearchService) -> None:
        self.search = search

    async def resolve_identity(
        self,
        extraction: MemoExtraction,
        limit_deals: int = 5,
        pipeline_id: Optional[str] = None,
        preferred_contact_id: Optional[str] = None,
    ) -> IdentityResolution:
        del pipeline_id
        result = IdentityResolution()

        if preferred_contact_id:
            try:
                person = await self.search.get_person(preferred_contact_id)
                if person.get("id") is not None:
                    result.selected = await _anchor(
                        person, self.search, reason="Explicit contact selection", confidence=1.0, limit_deals=limit_deals
                    )
                    result.company_id = result.selected.company_id
                    result.company_name = result.selected.company_name
                    return result
            except Exception as e:
                logger.warning("preferred Pipedrive person %s lookup failed: %s", preferred_contact_id, e)

        email = real_contact_email_or_none(extraction.contactEmail)
        phone = (extraction.contactPhone or "").strip() or None
        name = (extraction.contactName or "").strip() or None
        company_name = (extraction.companyName or "").strip() or None

        if email and is_real_contact_email(email):
            try:
                hits = await self.search.search_persons(email, fields="email", limit=5)
                exact = [p for p in hits if (primary_email(p) or "").lower() == email]
                pick = exact[0] if exact else None
                if pick and pick.get("id") is not None:
                    result.selected = await _anchor(
                        pick, self.search, reason="Contact email match", confidence=0.98, limit_deals=limit_deals
                    )
                    result.company_id = result.selected.company_id
                    result.company_name = result.selected.company_name
                    return result
            except Exception as e:
                logger.warning("Pipedrive email lookup failed for %s: %s", email, e)

        if phone:
            try:
                hits = await self.search.search_persons(phone, fields="phone", limit=5)
                if len(hits) == 1 and hits[0].get("id") is not None:
                    result.selected = await _anchor(
                        hits[0], self.search, reason="Contact phone match", confidence=0.92, limit_deals=limit_deals
                    )
                    result.company_id = result.selected.company_id
                    result.company_name = result.selected.company_name
                    return result
                if len(hits) > 1:
                    result.candidates = [
                        _to_contact_match(p, reason="Contact phone match", confidence=0.7) for p in hits if p.get("id") is not None
                    ]
                    return result
            except Exception as e:
                logger.warning("Pipedrive phone lookup failed: %s", e)

        if name:
            try:
                hits = await self.search.search_persons(name, fields="name", limit=5)
                if hits:
                    result.candidates = [
                        _to_contact_match(p, reason="Contact name match", confidence=0.55) for p in hits if p.get("id") is not None
                    ]
                    return result
            except Exception as e:
                logger.warning("Pipedrive name lookup failed: %s", e)

        if company_name:
            try:
                orgs = await self.search.search_organizations(company_name, limit=3)
                if orgs:
                    chosen = orgs[0]
                    result.company_id = str(chosen["id"]) if chosen.get("id") is not None else None
                    result.company_name = chosen.get("name") or company_name
            except Exception as e:
                logger.warning("Pipedrive company-only identity lookup failed: %s", e)

        return result

    async def resolve_contact_anchor(
        self,
        extraction: MemoExtraction,
        limit_deals: int = 5,
        pipeline_id: Optional[str] = None,
        preferred_contact_id: Optional[str] = None,
    ) -> Optional[ContactAnchor]:
        resolution = await self.resolve_identity(
            extraction,
            limit_deals=limit_deals,
            pipeline_id=pipeline_id,
            preferred_contact_id=preferred_contact_id,
        )
        return resolution.selected
