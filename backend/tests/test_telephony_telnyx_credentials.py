from unittest.mock import MagicMock, patch

from app.services.telephony.telnyx_credentials import (
    TOKEN_TTL_SECONDS_TELNYX,
    ensure_user_credential,
    mint_telnyx_voice_token,
)


def test_reuses_existing_row():
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {
            "credential_id": "cred-1",
            "sip_username": "userabc",
        }
    ]
    out = ensure_user_credential(supabase, "user-1")
    assert out == {"credentialId": "cred-1", "sipUsername": "userabc"}


def test_creates_and_inserts_when_missing():
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch(
        "app.services.telephony.telnyx_credentials.telnyx_rest"
    ) as telnyx_rest:
        telnyx_rest.return_value.create_telephony_credential.return_value = {
            "credential_id": "cred-new",
            "sip_username": "sip-new",
        }
        out = ensure_user_credential(supabase, "user-1")

    assert out == {"credentialId": "cred-new", "sipUsername": "sip-new"}
    telnyx_rest.return_value.create_telephony_credential.assert_called_once_with(
        name="vocify-user-1"
    )
    inserted = supabase.table.return_value.insert.call_args.args[0]
    assert inserted == {
        "user_id": "user-1",
        "provider": "telnyx",
        "credential_id": "cred-new",
        "sip_username": "sip-new",
    }


def test_mint_uses_existing_credential():
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {
            "credential_id": "cred-1",
            "sip_username": "userabc",
        }
    ]
    with patch(
        "app.services.telephony.telnyx_credentials.telnyx_rest"
    ) as telnyx_rest:
        telnyx_rest.return_value.mint_credential_token.return_value = "jwt-token"
        out = mint_telnyx_voice_token(supabase, "user-1")

    telnyx_rest.return_value.mint_credential_token.assert_called_once_with("cred-1")
    assert out == {
        "token": "jwt-token",
        "identity": "user-1",
        "expiresIn": TOKEN_TTL_SECONDS_TELNYX,
        "provider": "telnyx",
    }
    assert TOKEN_TTL_SECONDS_TELNYX == 24 * 3600
