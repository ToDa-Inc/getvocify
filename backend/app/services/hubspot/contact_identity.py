"""
Contact-first identity resolution for HubSpot.

Cascade (first decisive win):
1. preferred_contact_id (extension page / UI candidate confirm)
2. Real email → auto-lock
3. Phone → auto-lock if exactly one match
4. First+last (+ optional company filter) → auto-lock if exactly one
5. Single-token name → auto-lock only if exactly one match
6. Company-only → company context without silent contact lock

Ambiguous sets return candidates for UI confirmation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.models.approval import ContactMatch, DealMatch
from app.models.memo import MemoExtraction
from .associations import HubSpotAssociationService
from .contacts import HubSpotContactService
from .search import HubSpotSearchService, split_person_name
from .types import HubSpotContact

logger = logging.getLogger(__name__)

PLACEHOLDER_EMAIL_SUFFIX = "@lead.getvocify.com"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_real_contact_email(email: Optional[str]) -> bool:
    if not email or not str(email).strip():
        return False
    e = str(email).strip().lower()
    if e.endswith(PLACEHOLDER_EMAIL_SUFFIX):
        return False
    if any(tok in e for tok in ("example.com", "test@", "noreply", "no-reply")):
        return False
    local, _, domain = e.partition("@")
    if not local or not domain or "." not in domain:
        return False
    return bool(_EMAIL_RE.match(e))


@dataclass
class ContactAnchor:
    contact_id: str
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None
    jobtitle: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    deal_matches: list[DealMatch] = field(default_factory=list)
    properties: dict = field(default_factory=dict)
    match_reason: str = "Contact email match"
    match_confidence: float = 0.98

    def to_contact_match(self) -> ContactMatch:
        return ContactMatch(
            contact_id=self.contact_id,
            email=self.email or "",
            name=self.name,
            phone=self.phone,
            jobtitle=self.jobtitle,
            company_id=self.company_id,
            company_name=self.company_name,
            match_confidence=self.match_confidence,
            match_reason=self.match_reason,
        )


@dataclass
class IdentityResolution:
    selected: Optional[ContactAnchor] = None
    candidates: list[ContactMatch] = field(default_factory=list)
    company_id: Optional[str] = None
    company_name: Optional[str] = None


def _nested_contact_props(extraction: MemoExtraction) -> dict[str, Any]:
    raw = getattr(extraction, "raw_data", None) or {}
    if isinstance(raw, dict):
        props = raw.get("contact_properties") or {}
        if isinstance(props, dict):
            return props
    # Also accept top-level nested bag if present on model dump
    dump = extraction.model_dump() if hasattr(extraction, "model_dump") else {}
    props = dump.get("contact_properties") if isinstance(dump, dict) else None
    return props if isinstance(props, dict) else {}


def extraction_email(extraction: MemoExtraction) -> Optional[str]:
    top = (extraction.contactEmail or "").strip() or None
    if top:
        return top
    nested = _nested_contact_props(extraction).get("email")
    if isinstance(nested, str) and nested.strip():
        return nested.strip()
    return None


def extraction_phone(extraction: MemoExtraction) -> Optional[str]:
    top = (extraction.contactPhone or "").strip() or None
    if top:
        return top
    nested = _nested_contact_props(extraction)
    for key in ("phone", "mobilephone", "mobile"):
        val = nested.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _display_name(props: dict) -> Optional[str]:
    name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
    return name or None


def _contact_to_match(
    contact: HubSpotContact,
    *,
    match_reason: str,
    confidence: float,
    company_id: Optional[str] = None,
    company_name: Optional[str] = None,
) -> ContactMatch:
    props = dict(contact.properties or {})
    return ContactMatch(
        contact_id=str(contact.id),
        email=(props.get("email") or "") or "",
        name=_display_name(props),
        phone=props.get("phone") or props.get("mobilephone"),
        jobtitle=props.get("jobtitle"),
        company_id=company_id,
        company_name=company_name,
        match_confidence=confidence,
        match_reason=match_reason,
    )


def _company_name_matches(candidate: Optional[str], needle: str) -> bool:
    if not candidate or not needle:
        return False
    a = candidate.strip().lower()
    b = needle.strip().lower()
    if not a or not b:
        return False
    return a == b or b in a or a in b


async def _enrich_props(
    contacts: Optional[HubSpotContactService],
    contact: HubSpotContact,
) -> dict:
    props = dict(contact.properties or {})
    if not contacts:
        return props
    try:
        full = await contacts.get(
            contact.id,
            properties=["email", "firstname", "lastname", "phone", "mobilephone", "jobtitle"],
        )
        if full and full.properties:
            props = {**props, **(full.properties or {})}
    except Exception:
        pass
    return props


async def _company_for_contact(
    associations: HubSpotAssociationService,
    search: HubSpotSearchService,
    contact_id: str,
) -> tuple[Optional[str], Optional[str]]:
    try:
        company_ids = await associations.get_associations("contacts", contact_id, "companies")
        if not company_ids:
            return None, None
        company_id = str(company_ids[0])
        company_name = None
        try:
            comp = await search.client.get(
                f"/crm/v3/objects/companies/{company_id}",
                params={"properties": "name,domain"},
            )
            if comp:
                company_name = (comp.get("properties") or {}).get("name")
        except Exception:
            pass
        return company_id, company_name
    except Exception as e:
        logger.warning("Contact→company associations failed: %s", e)
        return None, None


async def _deal_matches_for_contact(
    associations: HubSpotAssociationService,
    search: HubSpotSearchService,
    contact_id: str,
    *,
    contact_name: Optional[str],
    contact_email: str,
    company_name: Optional[str],
    limit_deals: int,
    pipeline_id: Optional[str],
    match_confidence: float = 0.95,
) -> list[DealMatch]:
    deal_matches: list[DealMatch] = []
    try:
        deal_ids = await associations.get_associations("contacts", contact_id, "deals")
        for did in deal_ids[: max(limit_deals * 2, limit_deals)]:
            try:
                deal_data = await search.client.get(
                    f"/crm/v3/objects/deals/{did}",
                    params={
                        "properties": "dealname,amount,dealstage,pipeline,hs_lastmodifieddate",
                    },
                )
            except Exception:
                continue
            if not deal_data:
                continue
            dprops = deal_data.get("properties") or {}
            if pipeline_id and dprops.get("pipeline") and dprops.get("pipeline") != pipeline_id:
                continue
            deal_matches.append(
                DealMatch(
                    deal_id=str(deal_data.get("id") or did),
                    deal_name=dprops.get("dealname") or "Deal",
                    company_name=company_name,
                    contact_name=contact_name,
                    contact_email=contact_email or None,
                    amount=dprops.get("amount"),
                    stage=dprops.get("dealstage"),
                    last_updated=dprops.get("hs_lastmodifieddate") or "",
                    match_confidence=match_confidence,
                    match_reason="Linked to matched contact",
                )
            )
            if len(deal_matches) >= limit_deals:
                break
    except Exception as e:
        logger.warning("Contact→deal associations failed: %s", e)
    return deal_matches


async def _anchor_from_contact(
    contact: HubSpotContact,
    *,
    search: HubSpotSearchService,
    associations: HubSpotAssociationService,
    contacts: Optional[HubSpotContactService],
    match_reason: str,
    match_confidence: float,
    limit_deals: int,
    pipeline_id: Optional[str],
) -> ContactAnchor:
    props = await _enrich_props(contacts, contact)
    name = _display_name(props)
    email = (props.get("email") or "").strip().lower()
    company_id, company_name = await _company_for_contact(associations, search, str(contact.id))
    deal_matches = await _deal_matches_for_contact(
        associations,
        search,
        str(contact.id),
        contact_name=name,
        contact_email=email,
        company_name=company_name,
        limit_deals=limit_deals,
        pipeline_id=pipeline_id,
        match_confidence=match_confidence,
    )
    return ContactAnchor(
        contact_id=str(contact.id),
        email=email,
        name=name,
        phone=props.get("phone") or props.get("mobilephone"),
        jobtitle=props.get("jobtitle"),
        company_id=company_id,
        company_name=company_name,
        deal_matches=deal_matches,
        properties=props,
        match_reason=match_reason,
        match_confidence=match_confidence,
    )


async def _candidates_from_contacts(
    contacts_list: list[HubSpotContact],
    *,
    search: HubSpotSearchService,
    associations: HubSpotAssociationService,
    match_reason: str,
    confidence: float,
) -> list[ContactMatch]:
    out: list[ContactMatch] = []
    for contact in contacts_list:
        company_id, company_name = await _company_for_contact(
            associations, search, str(contact.id)
        )
        out.append(
            _contact_to_match(
                contact,
                match_reason=match_reason,
                confidence=confidence,
                company_id=company_id,
                company_name=company_name,
            )
        )
    return out


async def _filter_by_company(
    contacts_list: list[HubSpotContact],
    company_name: str,
    *,
    search: HubSpotSearchService,
    associations: HubSpotAssociationService,
) -> list[HubSpotContact]:
    filtered: list[HubSpotContact] = []
    for contact in contacts_list:
        _, cname = await _company_for_contact(associations, search, str(contact.id))
        if _company_name_matches(cname, company_name):
            filtered.append(contact)
    return filtered


async def resolve_identity(
    extraction: MemoExtraction,
    search: HubSpotSearchService,
    associations: HubSpotAssociationService,
    contacts: Optional[HubSpotContactService] = None,
    limit_deals: int = 5,
    pipeline_id: Optional[str] = None,
    preferred_contact_id: Optional[str] = None,
) -> IdentityResolution:
    """Full cascade with lock-or-candidates result."""
    result = IdentityResolution()

    # 1) Explicit pick
    if preferred_contact_id:
        try:
            contact = await search.client.get(
                f"/crm/v3/objects/contacts/{preferred_contact_id}",
                params={
                    "properties": "email,firstname,lastname,phone,mobilephone,jobtitle",
                },
            )
            if contact and contact.get("id"):
                hs = HubSpotContact(**contact)
                result.selected = await _anchor_from_contact(
                    hs,
                    search=search,
                    associations=associations,
                    contacts=contacts,
                    match_reason="Explicit contact selection",
                    match_confidence=1.0,
                    limit_deals=limit_deals,
                    pipeline_id=pipeline_id,
                )
                result.company_id = result.selected.company_id
                result.company_name = result.selected.company_name
                return result
        except Exception as e:
            logger.warning("preferred contact %s lookup failed: %s", preferred_contact_id, e)

    email = extraction_email(extraction)
    phone = extraction_phone(extraction)
    name = (extraction.contactName or "").strip() or None
    company_name = (extraction.companyName or "").strip() or None

    # 2) Email
    if is_real_contact_email(email):
        try:
            found = await search.find_contact_by_email(email.strip().lower())
            if found:
                result.selected = await _anchor_from_contact(
                    found,
                    search=search,
                    associations=associations,
                    contacts=contacts,
                    match_reason="Contact email match",
                    match_confidence=0.98,
                    limit_deals=limit_deals,
                    pipeline_id=pipeline_id,
                )
                result.company_id = result.selected.company_id
                result.company_name = result.selected.company_name
                return result
        except Exception as e:
            logger.warning("Contact email lookup failed for %s: %s", email, e)

    # 3) Phone — unique only
    if phone:
        try:
            hits = await search.find_contacts_by_phone(phone, limit=5)
            if len(hits) == 1:
                result.selected = await _anchor_from_contact(
                    hits[0],
                    search=search,
                    associations=associations,
                    contacts=contacts,
                    match_reason="Contact phone match",
                    match_confidence=0.92,
                    limit_deals=limit_deals,
                    pipeline_id=pipeline_id,
                )
                result.company_id = result.selected.company_id
                result.company_name = result.selected.company_name
                return result
            if len(hits) > 1:
                result.candidates = await _candidates_from_contacts(
                    hits,
                    search=search,
                    associations=associations,
                    match_reason="Contact phone match",
                    confidence=0.7,
                )
                return result
        except Exception as e:
            logger.warning("Contact phone lookup failed: %s", e)

    # 4–5) Name (+ optional company). Lock when exactly one.
    first, last = split_person_name(name)
    if first:
        try:
            hits = await search.find_contacts_by_name(name, limit=5)
            if company_name and hits:
                company_hits = await _filter_by_company(
                    hits, company_name, search=search, associations=associations
                )
                if len(company_hits) == 1:
                    result.selected = await _anchor_from_contact(
                        company_hits[0],
                        search=search,
                        associations=associations,
                        contacts=contacts,
                        match_reason="Name + company match",
                        match_confidence=0.9,
                        limit_deals=limit_deals,
                        pipeline_id=pipeline_id,
                    )
                    result.company_id = result.selected.company_id
                    result.company_name = result.selected.company_name
                    return result
                if len(company_hits) > 1:
                    result.candidates = await _candidates_from_contacts(
                        company_hits,
                        search=search,
                        associations=associations,
                        match_reason="Name + company match",
                        confidence=0.65,
                    )
                    return result

            if len(hits) == 1:
                reason = "Contact name match" if last else "Contact name token match"
                conf = 0.88 if last else 0.78
                result.selected = await _anchor_from_contact(
                    hits[0],
                    search=search,
                    associations=associations,
                    contacts=contacts,
                    match_reason=reason,
                    match_confidence=conf,
                    limit_deals=limit_deals,
                    pipeline_id=pipeline_id,
                )
                result.company_id = result.selected.company_id
                result.company_name = result.selected.company_name
                return result
            if len(hits) > 1:
                reason = "Contact name match" if last else "Contact name token match"
                result.candidates = await _candidates_from_contacts(
                    hits,
                    search=search,
                    associations=associations,
                    match_reason=reason,
                    confidence=0.55 if last else 0.4,
                )
                return result
        except Exception as e:
            logger.warning("Contact name lookup failed: %s", e)

    # 6) Company-only — never invent a contact lock
    if company_name:
        try:
            companies = await search.find_companies_by_name(company_name, limit=3)
            if companies:
                chosen = None
                for c in companies:
                    cname = (c.properties or {}).get("name") or ""
                    if _company_name_matches(cname, company_name):
                        chosen = c
                        break
                chosen = chosen or companies[0]
                result.company_id = str(chosen.id)
                result.company_name = (chosen.properties or {}).get("name") or company_name
        except Exception as e:
            logger.warning("Company-only identity lookup failed: %s", e)

    return result


async def resolve_contact_anchor(
    extraction: MemoExtraction,
    search: HubSpotSearchService,
    associations: HubSpotAssociationService,
    contacts: Optional[HubSpotContactService] = None,
    limit_deals: int = 5,
    pipeline_id: Optional[str] = None,
    preferred_contact_id: Optional[str] = None,
) -> Optional[ContactAnchor]:
    """Backward-compatible: locked contact only (candidates ignored)."""
    resolution = await resolve_identity(
        extraction=extraction,
        search=search,
        associations=associations,
        contacts=contacts,
        limit_deals=limit_deals,
        pipeline_id=pipeline_id,
        preferred_contact_id=preferred_contact_id,
    )
    return resolution.selected
