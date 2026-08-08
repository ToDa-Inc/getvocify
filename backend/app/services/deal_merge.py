"""
Deal merge service for updating existing deals.

Deterministic merge: the user has already reviewed and edited the extraction
in the preview before approving. We apply user-approved values directly:
- description: replace with the latest AI summary (see merge_description below
  for why this is safe and doesn't lose history)
- scalar fields: use new value if present in extraction, else keep existing
- dealname: replace only if existing is generic ("New Deal", etc.)
No LLM - avoids extra latency and cost; preserves user intent.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).lower()


def merge_description(existing: Any, new: Any) -> Optional[str]:
    """
    Replace the deal's description with the latest AI-generated summary.

    This used to append every new summary onto the existing description
    (separated by "---"), intended to preserve history. In practice that just
    produces an ever-growing, unreadable blob on deals with several memos.
    Full history isn't actually lost: every sync attaches the verbatim
    transcript as a dated HubSpot Note on the deal (see hubspot/sync.py's
    transcript-note step), which is what a CRM timeline is for. So the
    description field can stay a short, current, readable snapshot instead.

    Returns None when no CRM update is needed (value already matches).
    """
    existing_s = str(existing or "").strip()
    new_s = str(new or "").strip()
    if not new_s:
        return existing_s or None
    if _normalize_text(new_s) == _normalize_text(existing_s):
        return None
    return new_s


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
        Deterministic: use new if present, else keep existing. Description is
        replaced with the latest summary (see merge_description).

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
        """Use new if present, else keep existing. Description is replaced, not appended."""
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
                merged_desc = merge_description(existing_val, new_val)
                if merged_desc is not None:
                    merged[f] = merged_desc
            elif new_val is not None and new_val != "":
                merged[f] = new_val
            elif existing_val is not None and existing_val != "":
                merged[f] = existing_val
        return merged
