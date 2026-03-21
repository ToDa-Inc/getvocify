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
        record_name_field: str = "dealname",
    ) -> dict[str, Any]:
        """
        Merge existing deal properties with new (CRM-native field names).
        Deterministic: use new if present, else keep existing. Description = append.

        Args:
            record_name_field: HubSpot "dealname" or Salesforce "Name", etc.
            transcript: Unused (kept for API compatibility)
        """
        return self._deterministic_merge(
            existing_properties,
            new_properties,
            allowed_fields,
            record_name_field=record_name_field,
        )

    def _deterministic_merge(
        self,
        existing: dict[str, Any],
        new: dict[str, Any],
        allowed_fields: list[str],
        record_name_field: str = "dealname",
    ) -> dict[str, Any]:
        """Use new if present, else keep existing. Description = append."""
        merged = {}
        generic_deal_names = ("new deal", "nuevo deal", "deal", "")
        existing_dealname = (existing.get(record_name_field) or "").strip().lower()
        for f in allowed_fields:
            if f in ("hs_object_id", "hs_createdate", "hs_lastmodifieddate"):
                continue
            if f == record_name_field and existing_dealname in generic_deal_names:
                new_val = new.get(record_name_field)
                if new_val:
                    merged[f] = new_val
                continue
            if f == record_name_field:
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
