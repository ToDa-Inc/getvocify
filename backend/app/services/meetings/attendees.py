"""Extract and enrich attendees from a calendar event.

Product rule: attendees come from the HubSpot contact linked to them + their email
matched from the event of the Google Calendar from the calendar API.

Extraction (calendar event):
- Get attendees from raw Google/Graph event
- Drop rooms/resources (reuse calendar_bots helpers, do not duplicate logic)
- Drop the rep themselves (by calendar email)
- Dedupe by lower-cased email
- Keep displayName when present
- Cap at 12

Enrichment (HubSpot, best-effort, never blocking):
- If company has connected HubSpot, look up attendees' emails as HubSpot contacts
- Use contact's full name as precedence: HubSpot contact name > calendar displayName > None
- Include the contact already linked to the memo when its email not in attendee list
- Any lookup failure -> keep calendar data; never block or raise
- No fake data, no placeholders

Output: [{"email": str, "name": str|None}]
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from supabase import Client

from app.integrations.recall_client import RecallClientError
from app.services.meetings.calendar_bots import _is_room
from app.services.hubspot.client import HubSpotClient
from app.services.hubspot.search import HubSpotSearchService

logger = logging.getLogger(__name__)

MAX_ATTENDEES = 12


def extract_attendees(
    raw_event: dict[str, Any],
    *,
    rep_email: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Extract attendees from a raw Google/Graph calendar event.

    Filters out rooms, the rep themselves, and dedupes by lower-cased email.
    Keeps calendar displayName when present. Caps at 12.

    Args:
        raw_event: The raw Google/Graph event (contains attendees and organizer)
        rep_email: Rep's calendar email to exclude from attendee list

    Returns:
        List of {email, name} dicts (name may be None)
    """
    if not isinstance(raw_event, dict):
        return []

    rep_email_norm = (rep_email or "").strip().lower() if rep_email else None
    seen_emails: set[str] = set()
    attendees: list[dict[str, Any]] = []

    # Process attendees
    for attendee in raw_event.get("attendees") or []:
        email = str(attendee.get("email") or (attendee.get("emailAddress") or {}).get("address") or "").strip().lower()
        if not email:
            continue
        if _is_room(attendee, email):
            continue
        if rep_email_norm and email == rep_email_norm:
            continue
        if email in seen_emails:
            continue

        seen_emails.add(email)
        name = str(attendee.get("displayName") or "").strip() or None
        attendees.append({"email": email, "name": name})

    # Process organizer
    organizer = raw_event.get("organizer") or {}
    organizer_email = str(organizer.get("email") or (organizer.get("emailAddress") or {}).get("address") or "").strip().lower()
    if organizer_email and organizer_email not in seen_emails:
        if not (rep_email_norm and organizer_email == rep_email_norm):
            seen_emails.add(organizer_email)
            name = str(organizer.get("displayName") or "").strip() or None
            attendees.append({"email": organizer_email, "name": name})

    return attendees[:MAX_ATTENDEES]


async def enrich_attendees_with_hubspot(
    supabase: Client,
    attendees: list[dict[str, Any]],
    company_id: Optional[str],
    linked_contact_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Enrich attendees with HubSpot contact names.

    Best-effort enrichment: any lookup failure keeps calendar data and does not raise.
    Name precedence: HubSpot contact name > calendar displayName > None.
    Includes the memo's linked contact when its email not already in attendee list.

    Args:
        supabase: Supabase client
        attendees: List of {email, name} dicts from extract_attendees
        company_id: Company ID (used to check HubSpot connection)
        linked_contact_id: HubSpot contact ID already linked to the memo (optional)

    Returns:
        Enriched attendee list (same structure, names potentially updated)
    """
    if not attendees or not company_id:
        return attendees

    try:
        # Check if company has HubSpot connected; if not, return calendar data as-is
        rows = supabase.table("crm_connections").select("*").eq("company_id", company_id).eq("crm_type", "hubspot").limit(1).execute().data or []
        if not rows:
            return attendees

        connection = rows[0]
        access_token = (connection.get("access_token") or "").strip()
        if not access_token:
            return attendees

        try:
            hs_client = HubSpotClient(access_token)
            search_service = HubSpotSearchService(hs_client)
        except Exception:
            return attendees

        # Build map: email -> attendee (for updates)
        attendee_by_email = {a["email"]: a for a in attendees}
        emails_to_lookup = set(a["email"] for a in attendees)

        # Enrich each email via HubSpot search
        for email in emails_to_lookup:
            try:
                contact = await search_service.find_contact_by_email(email)
                if contact and contact.properties:
                    # Extract full name from HubSpot contact
                    first = (contact.properties.get("firstname") or "").strip()
                    last = (contact.properties.get("lastname") or "").strip()
                    hs_name = f"{first} {last}".strip() if first or last else None
                    if hs_name:
                        attendee_by_email[email]["name"] = hs_name
            except Exception as exc:
                logger.debug("HubSpot lookup failed for attendee %s: %s", email, exc)
                # Keep calendar data; never block or raise

        # Add linked contact if not already in list
        if linked_contact_id:
            try:
                contact_resp = await hs_client.get(f"/crm/v3/objects/contacts/{linked_contact_id}", query_params={"properties": ["firstname", "lastname", "email"]})
                if contact_resp and contact_resp.get("properties"):
                    props = contact_resp["properties"]
                    email = (props.get("email") or "").strip().lower()
                    if email and email not in attendee_by_email:
                        first = (props.get("firstname") or "").strip()
                        last = (props.get("lastname") or "").strip()
                        name = f"{first} {last}".strip() if first or last else None
                        attendee_by_email[email] = {"email": email, "name": name}
            except Exception as exc:
                logger.debug("Linked contact enrichment failed: %s", exc)
                # Keep what we have; never block

        return list(attendee_by_email.values())[:MAX_ATTENDEES]
    except Exception as exc:
        logger.debug("Attendee enrichment failed (returning calendar data): %s", exc)
        return attendees
