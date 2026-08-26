from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException

from app.api.calls import CallerIdRequest, create_caller_id, mint_voice_access_token


class TestMintVoiceAccessToken:
    def _settings(self, settings):
        settings.TWILIO_ACCOUNT_SID = "AC" + "0" * 32
        settings.TWILIO_AUTH_TOKEN = "auth-token"
        settings.TWILIO_API_KEY_SID = "SK" + "0" * 32
        settings.TWILIO_API_KEY_SECRET = "api-secret"
        settings.TWILIO_TWIML_APP_SID = "AP" + "0" * 32

    def test_identity_is_the_vocify_user_id(self):
        with patch("app.api.calls.settings") as settings:
            self._settings(settings)
            token = mint_voice_access_token("11111111-2222-3333-4444-555555555555")

        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["grants"]["identity"] == "11111111-2222-3333-4444-555555555555"

    def test_grant_points_at_the_twiml_app(self):
        with patch("app.api.calls.settings") as settings:
            self._settings(settings)
            token = mint_voice_access_token("user-1")

        claims = jwt.decode(token, options={"verify_signature": False})
        voice = claims["grants"]["voice"]
        assert voice["outgoing"]["application_sid"] == "AP" + "0" * 32

    def test_incoming_calls_are_not_granted(self):
        # Outbound only: callbacks ring the SDR's real phone, not the browser.
        with patch("app.api.calls.settings") as settings:
            self._settings(settings)
            token = mint_voice_access_token("user-1")

        claims = jwt.decode(token, options={"verify_signature": False})
        assert "incoming" not in claims["grants"]["voice"]

    def test_raises_503_when_twilio_is_not_configured(self):
        with patch("app.api.calls.settings") as settings:
            settings.TWILIO_ACCOUNT_SID = None
            settings.TWILIO_API_KEY_SID = None
            settings.TWILIO_API_KEY_SECRET = None
            settings.TWILIO_TWIML_APP_SID = None
            with pytest.raises(HTTPException) as exc:
                mint_voice_access_token("user-1")

        assert exc.value.status_code == 503


class TestCreateCallerId:
    @pytest.mark.asyncio
    async def test_already_verified_normalizes_verification_code(self):
        with (
            patch("app.api.calls.telephony_configured", return_value=True),
            patch("app.api.calls.start_caller_id_verification") as mock_start,
        ):
            mock_start.return_value = {
                "phoneNumber": "+34600111222",
                "status": "verified",
                "validationSid": "CA123",
                "alreadyVerified": True,
            }
            result = await create_caller_id(
                body=CallerIdRequest(phoneNumber="+34600111222"),
                supabase=MagicMock(),
                user_id="user-1",
            )

        assert result["alreadyVerified"] is True
        assert "verificationCode" in result
        assert result["verificationCode"] is None
