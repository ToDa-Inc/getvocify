"""Official Pipedrive UI record URLs.

Deal:  https://{company_domain}.pipedrive.com/deal/{id}
Person: https://{company_domain}.pipedrive.com/person/{id}
  (tutorials: getting-details-of-a-deal, updating-a-person)

Organization uses the same company-host pattern as deal/person in the Pipedrive
web app (`/organization/{id}`). Not used on SyncResult — only extension parse.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

_UI_PATH = {
    "deal": "deal",
    "person": "person",
    "contact": "person",
    "organization": "organization",
    "company": "organization",
}

_NOT_COMPANY = frozenset({"api", "oauth", "www", "developers", "app"})


def company_domain_from_api_domain(api_domain: Optional[str]) -> Optional[str]:
    if not api_domain:
        return None
    raw = str(api_domain).strip()
    if not raw:
        return None
    host = (urlparse(raw if "://" in raw else f"https://{raw}").hostname or "").lower()
    if not host.endswith(".pipedrive.com"):
        return None
    sub = host.split(".")[0]
    if sub in _NOT_COMPANY:
        return None
    return sub


def build_pipedrive_record_url(company_domain: str, object_type: str, record_id: str) -> str:
    path = _UI_PATH[object_type]
    return f"https://{company_domain}.pipedrive.com/{path}/{record_id}"
