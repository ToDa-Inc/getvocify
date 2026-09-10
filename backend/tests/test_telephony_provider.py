from unittest.mock import patch

from app.services.telephony.provider import calling_provider, telephony_configured


def test_default_provider_is_twilio():
    with patch("app.services.telephony.provider.settings") as settings:
        settings.CALLING_PROVIDER = "twilio"
        settings.TWILIO_ACCOUNT_SID = "ACxxx"
        settings.TWILIO_AUTH_TOKEN = "tok"
        settings.TWILIO_API_KEY_SID = "SKxxx"
        settings.TWILIO_API_KEY_SECRET = "sec"
        settings.TWILIO_TWIML_APP_SID = "APxxx"
        settings.TELNYX_API_KEY = None
        settings.TELNYX_PUBLIC_KEY = None
        settings.TELNYX_CONNECTION_ID = None
        assert calling_provider() == "twilio"
        assert telephony_configured() is True


def test_telnyx_needs_key_connection_and_public_key():
    with patch("app.services.telephony.provider.settings") as settings:
        settings.CALLING_PROVIDER = "telnyx"
        settings.TELNYX_API_KEY = "KEY"
        settings.TELNYX_PUBLIC_KEY = "pub"
        settings.TELNYX_CONNECTION_ID = "conn"
        settings.TELNYX_CALL_CONTROL_APP_ID = "app"
        assert telephony_configured() is True
        settings.TELNYX_PUBLIC_KEY = None
        assert telephony_configured() is False
