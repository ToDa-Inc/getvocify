"""Which CRM record a browser page is, from its URL.

The desktop app sends the URLs of the CRM pages open in the rep's browsers,
front window first. Same URL shapes as the extension's parsers
(chrome-extension/lib/hubspot-parser.js, pipedrive-parser.js).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal, Optional, Union

Provider = Literal["hubspot", "pipedrive"]
ObjectType = Literal["contact", "company", "deal"]


@dataclass(frozen=True)
class CrmRecord:
    provider: Provider
    object_type: ObjectType
    record_id: str
    # HubSpot portal id or Pipedrive company domain, to check against the connection.
    account_id: Optional[str]


@dataclass(frozen=True)
class CrmPage:
    """A CRM page that is not a record: a list, a sequence, the inbox."""

    provider: Provider


_HUBSPOT_APP = re.compile(r"^https://app(?:-[a-z0-9]+)?\.hubspot\.com/", re.I)
_HUBSPOT_RECORD = re.compile(r"\.hubspot\.com/contacts/(\d+)/record/(0-[123])/(\d+)", re.I)
_HUBSPOT_LEGACY = re.compile(r"\.hubspot\.com/contacts/(\d+)/(contact|company|deal)/(\d+)", re.I)
# HubSpot's calling window and calling frames are not where the rep is.
_HUBSPOT_CALLING = re.compile(
    r"\.hubspot\.com/(?:calling-integration-popup-ui|calling-cross-tab-embed|calling)/", re.I
)
_HUBSPOT_TYPES = {"0-1": "contact", "0-2": "company", "0-3": "deal"}

_PIPEDRIVE_APP = re.compile(r"^https://(?!(?:api|oauth|www|developers|app)\.)([a-z0-9-]+)\.pipedrive\.com/", re.I)
_PIPEDRIVE_RECORD = re.compile(r"\.pipedrive\.com/(deal|person|organization)/(\d+)", re.I)
_PIPEDRIVE_TYPES = {"deal": "deal", "person": "contact", "organization": "company"}


def parse_crm_url(url: str) -> Union[CrmRecord, CrmPage, None]:
    """A record, a non-record CRM page, or None (not the CRM, or a calling window)."""
    if not url or not isinstance(url, str):
        return None
    if _HUBSPOT_APP.match(url):
        if _HUBSPOT_CALLING.search(url):
            return None
        m = _HUBSPOT_RECORD.search(url)
        if m:
            return CrmRecord("hubspot", _HUBSPOT_TYPES[m.group(2)], m.group(3), m.group(1))  # type: ignore[arg-type]
        m = _HUBSPOT_LEGACY.search(url)
        if m:
            return CrmRecord("hubspot", m.group(2).lower(), m.group(3), m.group(1))  # type: ignore[arg-type]
        return CrmPage("hubspot")
    app = _PIPEDRIVE_APP.match(url)
    if app:
        m = _PIPEDRIVE_RECORD.search(url)
        if m:
            return CrmRecord("pipedrive", _PIPEDRIVE_TYPES[m.group(1).lower()], m.group(2), app.group(1).lower())  # type: ignore[arg-type]
        return CrmPage("pipedrive")
    return None


def record_on_screen(urls: Iterable[str]) -> Optional[CrmRecord]:
    """The record the rep is on: the front-most CRM page, if it is a record.

    A front-most list or sequence page means the call has no known contact,
    even when an older window still shows a record.
    """
    for url in urls:
        parsed = parse_crm_url(url)
        if parsed is None:
            continue
        return parsed if isinstance(parsed, CrmRecord) else None
    return None
