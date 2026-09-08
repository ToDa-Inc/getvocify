"""Twilio REST client factory.

Kept in its own module so tests can patch a single seam and so the rest of the
telephony package never reads credentials directly.
"""

from __future__ import annotations

from functools import lru_cache

from twilio.rest import Client as TwilioRestClient

from app.config import settings
from app.services.telephony.provider import telephony_configured as telephony_configured


class TelephonyNotConfigured(RuntimeError):
    """Twilio credentials are absent; calling features are unavailable."""


@lru_cache(maxsize=1)
def _client(
    account_sid: str,
    auth_token: str,
    edge: str | None,
    region: str | None,
) -> TwilioRestClient:
    kwargs = {}
    if edge and region:
        kwargs["edge"] = edge
        kwargs["region"] = region
    return TwilioRestClient(account_sid, auth_token, **kwargs)


def twilio_rest() -> TwilioRestClient:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise TelephonyNotConfigured("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN unset")
    return _client(
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_AUTH_TOKEN,
        settings.TWILIO_EDGE or None,
        settings.TWILIO_REGION or None,
    )
