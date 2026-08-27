"""One-time registration of Vocify as HubSpot's recording provider.

Run once per HubSpot app id, not per customer. HubSpot substitutes `%s` in the
registered URL with the engagement's `hs_call_external_id`.
"""

from __future__ import annotations

from typing import Any

from app.services.hubspot.call_log import CALLING_EXTENSIONS_BASE
from app.services.hubspot.client import HubSpotClient

RECORDING_PATH_TEMPLATE = "/public/hubspot/recordings/%s"


def recording_endpoint_url(public_base_url: str) -> str:
    return f"{(public_base_url or '').rstrip('/')}{RECORDING_PATH_TEMPLATE}"


async def register_recording_endpoint(
    client: HubSpotClient,
    app_id: str,
    endpoint_url: str,
) -> dict[str, Any]:
    if "%s" not in endpoint_url:
        raise ValueError("endpoint_url must contain the %s placeholder")
    return await client.post(
        f"{CALLING_EXTENSIONS_BASE}/{app_id}/settings/recording",
        data={"urlToRetrieveAuthedRecording": endpoint_url},
    ) or {}
