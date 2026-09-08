from __future__ import annotations

from typing import Literal

from app.config import settings

CallingProvider = Literal["twilio", "telnyx"]


def calling_provider() -> CallingProvider:
    value = (settings.CALLING_PROVIDER or "twilio").strip().lower()
    if value == "telnyx":
        return "telnyx"
    return "twilio"


def telephony_configured() -> bool:
    if calling_provider() == "telnyx":
        return bool(
            settings.TELNYX_API_KEY
            and settings.TELNYX_PUBLIC_KEY
            and settings.TELNYX_CONNECTION_ID
        )
    return bool(
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_API_KEY_SID
        and settings.TWILIO_API_KEY_SECRET
        and settings.TWILIO_TWIML_APP_SID
    )
