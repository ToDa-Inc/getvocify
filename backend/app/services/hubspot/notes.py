"""
Shared helper for creating a HubSpot note associated to whichever of
deal/contact/company exist, with the same primary-then-fallback
association strategy sync.py's Step 7 uses for the main transcript note:
try one call with associations inline, and if HubSpot rejects the request
before creating anything (403/400/404 - see the exception list below),
retry with a bare create then associate individually so one failed
association can't cost the whole note.

Used by call_outcome.py's standalone Lost-reason note. Step 7 itself keeps
its own inline copy of this logic (not refactored to call this helper) -
it has extra happy-path logging this generic version doesn't need, and it
predates this module; left alone to avoid touching a delicate, already
correct, heavily-commented code path for a feature that doesn't need it to
change.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.logging_config import log_domain, DOMAIN_HUBSPOT

from .associations import HubSpotAssociationService
from .client import HubSpotClient
from .exceptions import HubSpotNotFoundError, HubSpotScopeError, HubSpotValidationError

logger = logging.getLogger(__name__)


async def create_note_with_associations(
    client: HubSpotClient,
    associations: HubSpotAssociationService,
    *,
    note_properties: dict[str, Any],
    deal_id: Optional[str],
    contact_id: Optional[str],
    company_id: Optional[str],
    memo_id: str,
    log_event: str,
) -> Optional[str]:
    """Returns the created note's id, or None if HubSpot returned no id
    (callers decide what that means - typically treated as a failure)."""
    note_targets: list[tuple[str, str, int]] = []
    if deal_id:
        note_targets.append(("deals", str(deal_id), associations.NOTE_TO_DEAL))
    if contact_id:
        note_targets.append(("contacts", str(contact_id), associations.NOTE_TO_CONTACT))
    if company_id:
        note_targets.append(("companies", str(company_id), associations.NOTE_TO_COMPANY))

    try:
        created = await client.post(
            "/crm/v3/objects/notes",
            data={
                "properties": note_properties,
                "associations": [
                    {
                        "to": {"id": to_id},
                        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": type_id}],
                    }
                    for _, to_id, type_id in note_targets
                ],
            },
        )
        return (created or {}).get("id")
    except (HubSpotScopeError, HubSpotValidationError, HubSpotNotFoundError) as e:
        # Same reasoning as Step 7: these are pre-creation validation
        # failures per HubSpot's API, so the note above was never
        # persisted - a bare retry cannot produce a duplicate.
        logger.warning(
            "⚠️ %s: note create with associations failed (safe to retry bare): %s",
            log_event, e,
            extra=log_domain(DOMAIN_HUBSPOT, f"{log_event}_assoc_failed", memo_id=memo_id),
        )
        created = await client.post("/crm/v3/objects/notes", data={"properties": note_properties})
        note_id = (created or {}).get("id")
        if note_id:
            for object_type, to_id, _type_id in note_targets:
                try:
                    await associations.create_association("notes", note_id, object_type, to_id)
                except Exception as assoc_e:
                    logger.warning(
                        "⚠️ %s: failed to associate note %s to %s %s: %s",
                        log_event, note_id, object_type, to_id, assoc_e,
                        extra=log_domain(DOMAIN_HUBSPOT, f"{log_event}_association_failed", memo_id=memo_id),
                    )
        return note_id
