"""
HubSpot account hosting / UI domain resolution for correct CRM deep links.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .client import HubSpotClient


@dataclass(frozen=True)
class HubSpotAccountContext:
    portal_id: str
    region: str = "na1"
    ui_domain: Optional[str] = None


def infer_region_from_token(access_token: str) -> str:
    """Private App tokens embed region: pat-eu1-..., pat-na1-..."""
    token = (access_token or "").strip()
    if token.startswith("pat-"):
        parts = token.split("-")
        if len(parts) >= 3 and parts[1] and not parts[1][0].isdigit():
            return parts[1]
    return "na1"


OBJECT_TYPE_CONTACT = "0-1"
OBJECT_TYPE_COMPANY = "0-2"
OBJECT_TYPE_DEAL = "0-3"


def _record_host(*, ui_domain: Optional[str] = None, region: str = "na1") -> str:
    host = (ui_domain or "").strip().rstrip("/")
    if host.startswith("https://"):
        host = host[8:]
    elif host.startswith("http://"):
        host = host[7:]
    if not host:
        region_prefix = f"-{region}" if region and region != "na1" else ""
        host = f"app{region_prefix}.hubspot.com"
    return host


def build_record_url(
    portal_id: str,
    record_id: str,
    object_type_id: str,
    *,
    ui_domain: Optional[str] = None,
    region: str = "na1",
) -> str:
    host = _record_host(ui_domain=ui_domain, region=region)
    return f"https://{host}/contacts/{portal_id}/record/{object_type_id}/{record_id}"


def build_deal_record_url(
    portal_id: str,
    deal_id: str,
    *,
    ui_domain: Optional[str] = None,
    region: str = "na1",
) -> str:
    """Build HubSpot deal record URL using account uiDomain when available."""
    return build_record_url(
        portal_id, deal_id, OBJECT_TYPE_DEAL, ui_domain=ui_domain, region=region
    )


def build_contact_record_url(
    portal_id: str,
    contact_id: str,
    *,
    ui_domain: Optional[str] = None,
    region: str = "na1",
) -> str:
    return build_record_url(
        portal_id, contact_id, OBJECT_TYPE_CONTACT, ui_domain=ui_domain, region=region
    )


def build_company_record_url(
    portal_id: str,
    company_id: str,
    *,
    ui_domain: Optional[str] = None,
    region: str = "na1",
) -> str:
    return build_record_url(
        portal_id, company_id, OBJECT_TYPE_COMPANY, ui_domain=ui_domain, region=region
    )


async def resolve_account_context(client: HubSpotClient) -> HubSpotAccountContext:
    """
    Resolve portal ID, data center region, and UI domain for deep links.

    Prefer account-info v3 (includes uiDomain + dataHostingLocation for OAuth tokens).
    Fall back to legacy /integrations/v1/me + token prefix inference.
    """
    details: Optional[dict[str, Any]] = None
    try:
        details = await client.get("/account-info/v3/details")
    except Exception:
        details = None

    if details and details.get("portalId"):
        region = (details.get("dataHostingLocation") or infer_region_from_token(client.access_token) or "na1").strip()
        ui_domain = details.get("uiDomain")
        return HubSpotAccountContext(
            portal_id=str(details["portalId"]),
            region=region or "na1",
            ui_domain=str(ui_domain).strip() if ui_domain else None,
        )

    account_info = await client.get("/integrations/v1/me")
    if not account_info or not account_info.get("portalId"):
        raise RuntimeError("Failed to retrieve HubSpot account information")

    region = infer_region_from_token(client.access_token)
    return HubSpotAccountContext(
        portal_id=str(account_info["portalId"]),
        region=region,
        ui_domain=None,
    )
