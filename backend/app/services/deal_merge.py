"""
Deal merge service for updating existing deals.

Deterministic merge: the user has already reviewed and edited the extraction
in the preview before approving. We apply user-approved values directly:
- description: append new to existing (keep history)
- scalar fields: use new value if present in extraction, else keep existing
- dealname: replace only if existing is generic ("New Deal", etc.)
No LLM - avoids extra latency and cost; preserves user intent.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DealMergeService:
    """
    Merges new extraction with existing deal properties.
    Deterministic rules only - user has already approved the values in the UI.
    """

    def merge_properties(
        self,
        existing_properties: dict[str, Any],
        new_properties: dict[str, Any],
        allowed_fields: list[str],
        transcript: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Merge existing deal properties with new (already mapped to HubSpot format).
        Deterministic: use new if present, else keep existing. Description = append.

        Args:
            existing_properties: Current deal properties from HubSpot
            new_properties: New properties from map_extraction_to_properties_with_stage
            allowed_fields: Fields we're allowed to update
            transcript: Unused (kept for API compatibility)

        Returns:
            Merged properties dict (HubSpot format, only fields to update)
        """
        return self._deterministic_merge(
            existing_properties, new_properties, allowed_fields
        )

    def _deterministic_merge(
        self,
        existing: dict[str, Any],
        new: dict[str, Any],
        allowed_fields: list[str],
    ) -> dict[str, Any]:
        """Use new if present, else keep existing. Description = append."""
        merged = {}
        generic_deal_names = ("new deal", "nuevo deal", "deal", "")
        existing_dealname = (existing.get("dealname") or "").strip().lower()
        for f in allowed_fields:
            if f in ("hs_object_id", "hs_createdate", "hs_lastmodifieddate"):
                continue
            if f == "dealname" and existing_dealname in generic_deal_names:
                new_val = new.get("dealname")
                if new_val:
                    merged[f] = new_val
                continue
            if f == "dealname":
                continue
            new_val = new.get(f)
            existing_val = existing.get(f)
            if f == "description":
                if new_val and existing_val:
                    merged[f] = f"{existing_val}\n\n---\n\n{new_val}"
                elif new_val:
                    merged[f] = new_val
                elif existing_val:
                    pass
            elif new_val is not None and new_val != "":
                merged[f] = new_val
            elif existing_val is not None and existing_val != "":
                merged[f] = existing_val
        return merged
