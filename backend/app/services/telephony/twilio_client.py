"""Twilio REST client factory.

Kept in its own module so tests can patch a single seam and so the rest of the
telephony package never reads credentials directly.
"""

from __future__ import annotations

from functools import lru_cache

from twilio.rest import Client as TwilioRestClient

from app.config import settings


class TelephonyNotConfigured(RuntimeError):
    """Twilio credentials are absent; calling features are unavailable."""


def telephony_configured() -> bool:
    return bool(
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_API_KEY_SID
        and settings.TWILIO_API_KEY_SECRET
        and settings.TWILIO_TWIML_APP_SID
    )


@lru_cache(maxsize=1)
def _client(account_sid: str, auth_token: str) -> TwilioRestClient:
    return TwilioRestClient(account_sid, auth_token)


def twilio_rest() -> TwilioRestClient:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise TelephonyNotConfigured("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN unset")
    return _client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
