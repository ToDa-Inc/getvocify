from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException

from app.api.calls import (
    CallerIdConfirmRequest,
    CallerIdRequest,
    confirm_caller_id,
    create_caller_id,
    create_voice_token,
    get_calling_config,
    mint_voice_access_token,
)
from app.services.telephony.telnyx_client import TelnyxNotConfigured


class TestMintVoiceAccessToken:
    def _settings(self, settings):
        settings.TWILIO_ACCOUNT_SID = "AC" + "0" * 32
        settings.TWILIO_AUTH_TOKEN = "auth-token"
        settings.TWILIO_API_KEY_SID = "SK" + "0" * 32
        settings.TWILIO_API_KEY_SECRET = "api-secret"
        settings.TWILIO_TWIML_APP_SID = "AP" + "0" * 32
        settings.TWILIO_REGION = None

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

    def test_ireland_region_is_in_the_jwt_header(self):
        with patch("app.api.calls.settings") as settings:
            self._settings(settings)
            settings.TWILIO_REGION = "ie1"
            token = mint_voice_access_token("user-1")

        assert jwt.get_unverified_header(token)["twr"] == "ie1"

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


class TestConfirmCallerId:
    @pytest.mark.asyncio
    async def test_twilio_confirm_does_not_call_telnyx(self):
        with (
            patch("app.api.calls.calling_provider", return_value="twilio"),
            patch("app.api.calls.confirm_caller_id_verification") as mock_confirm,
        ):
            with pytest.raises(HTTPException) as exc:
                await confirm_caller_id(
                    body=CallerIdConfirmRequest(
                        phoneNumber="+34600111222", code="482913"
                    ),
                    supabase=MagicMock(),
                    user_id="user-1",
                )

        assert exc.value.status_code in (400, 404)
        mock_confirm.assert_not_called()


class TestCallingConfigProvider:
    @pytest.mark.asyncio
    async def test_config_includes_provider(self):
        with (
            patch("app.api.calls.telephony_configured", return_value=False),
            patch("app.api.calls.calling_provider", return_value="twilio"),
        ):
            result = await get_calling_config(
                supabase=MagicMock(), user_id="user-1"
            )
        assert result["provider"] == "twilio"

    @pytest.mark.asyncio
    async def test_config_provisions_telnyx_credential(self):
        with (
            patch("app.api.calls.telephony_configured", return_value=True),
            patch("app.api.calls.calling_provider", return_value="telnyx"),
            patch("app.api.calls.ensure_user_credential") as ensure,
            patch("app.api.calls.list_caller_ids", return_value=[]),
        ):
            supabase = MagicMock()
            result = await get_calling_config(
                supabase=supabase, user_id="user-1"
            )
        ensure.assert_called_once_with(supabase, "user-1")
        assert result["provider"] == "telnyx"
        assert result["enabled"] is True


class TestCreateVoiceToken:
    @pytest.mark.asyncio
    async def test_twilio_response_includes_provider(self):
        with (
            patch("app.api.calls.calling_provider", return_value="twilio"),
            patch("app.api.calls.mint_voice_access_token", return_value="twilio-jwt"),
        ):
            result = await create_voice_token(
                supabase=MagicMock(), user_id="user-1"
            )
        assert result == {
            "token": "twilio-jwt",
            "identity": "user-1",
            "expiresIn": 3600,
            "provider": "twilio",
        }

    @pytest.mark.asyncio
    async def test_telnyx_mint_does_not_call_twilio_access_token(self):
        with (
            patch("app.api.calls.calling_provider", return_value="telnyx"),
            patch("app.api.calls.mint_telnyx_voice_token") as mint_telnyx,
            patch("app.api.calls.AccessToken") as access_token,
            patch("app.api.calls.mint_voice_access_token") as mint_twilio,
        ):
            mint_telnyx.return_value = {
                "token": "telnyx-jwt",
                "identity": "user-1",
                "expiresIn": 86400,
                "provider": "telnyx",
            }
            result = await create_voice_token(
                supabase=MagicMock(), user_id="user-1"
            )

        assert result["provider"] == "telnyx"
        assert result["token"] == "telnyx-jwt"
        assert result["expiresIn"] == 86400
        access_token.assert_not_called()
        mint_twilio.assert_not_called()
        mint_telnyx.assert_called_once()

    @pytest.mark.asyncio
    async def test_telnyx_token_raises_503_when_not_configured(self):
        with (
            patch("app.api.calls.calling_provider", return_value="telnyx"),
            patch(
                "app.api.calls.mint_telnyx_voice_token",
                side_effect=TelnyxNotConfigured(
                    "TELNYX_API_KEY / TELNYX_CONNECTION_ID unset"
                ),
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                await create_voice_token(supabase=MagicMock(), user_id="user-1")

        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_telnyx_config_raises_503_when_not_configured(self):
        with (
            patch("app.api.calls.telephony_configured", return_value=True),
            patch("app.api.calls.calling_provider", return_value="telnyx"),
            patch(
                "app.api.calls.ensure_user_credential",
                side_effect=TelnyxNotConfigured(
                    "TELNYX_API_KEY / TELNYX_CONNECTION_ID unset"
                ),
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                await get_calling_config(supabase=MagicMock(), user_id="user-1")

        assert exc.value.status_code == 503
