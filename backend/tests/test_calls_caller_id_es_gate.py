"""Spanish caller-ID range gate: Orden TDF/149/2025 art. 9 + Resolución SETID 14-04-2026 (400)."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.calls import (
    CallerIdConfirmRequest,
    CallerIdRequest,
    confirm_caller_id,
    create_caller_id,
    remove_caller_id,
)
from app.config import settings
from app.services.telephony.caller_id import (
    CallerIdNotVerified,
    CallerIdRangeRestricted,
    confirm_caller_id_verification,
    list_caller_ids,
    resolve_caller_id,
    spanish_cli_restriction,
    start_caller_id_verification,
)
from tests.test_telephony_caller_id import fake_supabase

BEFORE = date(2026, 10, 16)
ON = date(2026, 10, 17)


def _verified(number, *, user="user-1", is_default=False):
    return {
        "user_id": user,
        "phone_number": number,
        "status": "verified",
        "label": None,
        "is_default": is_default,
        "verified_at": "2026-01-01T00:00:00Z",
        "verification_sid": "CA-old",
    }


@pytest.fixture(autouse=True)
def _gate_defaults():
    with patch.multiple(
        settings,
        CALLING_ES_CLI_GATE_ENABLED=True,
        CALLING_ES_MOBILE_CALL_BLOCK_FROM=ON,
    ):
        yield


class TestClassification:
    @pytest.mark.parametrize(
        "number,expected",
        [
            ("+34600111222", "es_mobile"),
            ("+34699999999", "es_mobile"),
            ("+34712345678", "es_mobile"),
            ("+34400123456", "es_400"),
            ("+34910000000", None),
            ("+34930000000", None),
            ("+34800123456", None),
            ("+33612345678", None),
            ("+447700900123", None),
            ("+15555550100", None),
        ],
    )
    def test_ranges(self, number, expected):
        assert spanish_cli_restriction(number) == expected

    def test_default_call_block_date_is_the_400_deadline(self):
        from app.config import Settings

        assert Settings.model_fields["CALLING_ES_MOBILE_CALL_BLOCK_FROM"].default == ON
        assert Settings.model_fields["CALLING_ES_CLI_GATE_ENABLED"].default is True


class TestVerificationGate:
    @pytest.mark.parametrize("raw", ["600 111 222", "+34 712 345 678", "+34400123456"])
    @patch("app.services.telephony.caller_id.calling_provider", return_value="twilio")
    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_rejects_before_calling_the_provider(self, rest, _provider, raw):
        supabase, store = fake_supabase([])

        with pytest.raises(CallerIdRangeRestricted):
            start_caller_id_verification(supabase, "user-1", raw, label=None)

        rest.assert_not_called()
        assert store == []

    @patch("app.services.telephony.caller_id.calling_provider", return_value="telnyx")
    @patch("app.services.telephony.caller_id.telnyx_rest")
    def test_rejects_on_telnyx_too(self, telnyx, _provider):
        supabase, store = fake_supabase([])

        with pytest.raises(CallerIdRangeRestricted):
            start_caller_id_verification(supabase, "user-1", "+34600111222", label=None)

        telnyx.assert_not_called()
        assert store == []

    @patch("app.services.telephony.caller_id.calling_provider", return_value="twilio")
    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_spanish_landline_still_verifies(self, rest, _provider):
        rest.return_value.validation_requests.create.return_value = SimpleNamespace(
            validation_code="482913", friendly_name=None, call_sid="CA1"
        )
        supabase, store = fake_supabase([])

        result = start_caller_id_verification(supabase, "user-1", "910 111 222", label=None)

        assert result["phoneNumber"] == "+34910111222"
        assert store[0]["status"] == "pending"

    @patch("app.services.telephony.caller_id.calling_provider", return_value="twilio")
    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_foreign_mobile_still_verifies(self, rest, _provider):
        rest.return_value.validation_requests.create.return_value = SimpleNamespace(
            validation_code="111111", friendly_name=None, call_sid="CA2"
        )
        supabase, _ = fake_supabase([])

        result = start_caller_id_verification(supabase, "user-1", "+33612345678", label=None)

        assert result["status"] == "pending"

    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_already_verified_mobile_is_rejected_but_kept(self, rest):
        supabase, store = fake_supabase([_verified("+34600111222")])

        with pytest.raises(CallerIdRangeRestricted):
            start_caller_id_verification(supabase, "user-1", "+34600111222", label=None)

        rest.assert_not_called()
        assert store[0]["status"] == "verified"

    @patch("app.services.telephony.caller_id.calling_provider", return_value="twilio")
    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_flag_off_disables_the_gate(self, rest, _provider):
        rest.return_value.validation_requests.create.return_value = SimpleNamespace(
            validation_code="222222", friendly_name=None, call_sid="CA3"
        )
        supabase, store = fake_supabase([])

        with patch.object(settings, "CALLING_ES_CLI_GATE_ENABLED", False):
            start_caller_id_verification(supabase, "user-1", "+34600111222", label=None)

        assert store[0]["phone_number"] == "+34600111222"

    @patch("app.services.telephony.caller_id.telnyx_rest")
    def test_telnyx_confirm_of_a_pending_mobile_is_rejected_and_left_pending(self, telnyx):
        supabase, store = fake_supabase(
            [
                {
                    "user_id": "user-1",
                    "phone_number": "+34600111222",
                    "status": "pending",
                    "verification_sid": "+34600111222",
                    "verified_at": None,
                }
            ]
        )

        with pytest.raises(CallerIdRangeRestricted):
            confirm_caller_id_verification(supabase, "user-1", "+34600111222", "482913")

        telnyx.assert_not_called()
        assert store[0]["status"] == "pending"


class TestApiErrors:
    @pytest.mark.asyncio
    async def test_create_mobile_is_422_with_spanish_reason(self):
        supabase, store = fake_supabase([])
        with (
            patch("app.api.calls.telephony_configured", return_value=True),
            patch("app.services.telephony.caller_id.twilio_rest") as rest,
        ):
            with pytest.raises(HTTPException) as exc:
                await create_caller_id(
                    body=CallerIdRequest(phoneNumber="+34 600 111 222"),
                    supabase=supabase,
                    user_id="user-1",
                )

        assert exc.value.status_code == 422
        assert "móvil" in exc.value.detail.lower()
        assert "fijo" in exc.value.detail.lower()
        rest.assert_not_called()
        assert store == []

    @pytest.mark.asyncio
    async def test_create_400_is_422_with_spanish_reason(self):
        supabase, _ = fake_supabase([])
        with (
            patch("app.api.calls.telephony_configured", return_value=True),
            patch("app.services.telephony.caller_id.twilio_rest") as rest,
        ):
            with pytest.raises(HTTPException) as exc:
                await create_caller_id(
                    body=CallerIdRequest(phoneNumber="+34400123456"),
                    supabase=supabase,
                    user_id="user-1",
                )

        assert exc.value.status_code == 422
        assert "400" in exc.value.detail
        rest.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_mobile_is_422(self):
        supabase, _ = fake_supabase(
            [
                {
                    "user_id": "user-1",
                    "phone_number": "+34600111222",
                    "status": "pending",
                    "verification_sid": "+34600111222",
                    "verified_at": None,
                }
            ]
        )
        with (
            patch("app.api.calls.calling_provider", return_value="telnyx"),
            patch("app.services.telephony.caller_id.telnyx_rest") as telnyx,
        ):
            with pytest.raises(HTTPException) as exc:
                await confirm_caller_id(
                    body=CallerIdConfirmRequest(phoneNumber="+34600111222", code="482913"),
                    supabase=supabase,
                    user_id="user-1",
                )

        assert exc.value.status_code == 422
        telnyx.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocked_mobile_can_still_be_removed(self):
        supabase, store = fake_supabase([_verified("+34600111222")])
        with patch(
            "app.services.telephony.caller_id._release_twilio_outgoing_caller_id"
        ) as release:
            result = await remove_caller_id(
                phone_number="+34600111222", supabase=supabase, user_id="user-1"
            )

        assert result == {"ok": True}
        assert store == []
        release.assert_called_once_with("+34600111222")


class TestCallTimeGate:
    def test_existing_mobile_still_resolves_before_the_deadline(self):
        supabase, _ = fake_supabase([_verified("+34600111222", is_default=True)])

        assert (
            resolve_caller_id(supabase, "user-1", "+34600111222", today=BEFORE)
            == "+34600111222"
        )

    def test_existing_mobile_is_blocked_from_the_deadline_and_the_row_is_kept(self):
        supabase, store = fake_supabase([_verified("+34600111222", is_default=True)])

        with pytest.raises(CallerIdRangeRestricted) as exc:
            resolve_caller_id(supabase, "user-1", "+34600111222", today=ON)

        assert isinstance(exc.value, CallerIdNotVerified)
        assert "móvil" in str(exc.value).lower()
        assert store[0]["status"] == "verified"
        assert store[0]["is_default"] is True

    def test_default_mobile_falls_back_to_a_verified_landline(self):
        supabase, _ = fake_supabase(
            [
                _verified("+34600111222", is_default=True),
                _verified("+34910000000"),
            ]
        )

        assert resolve_caller_id(supabase, "user-1", None, today=ON) == "+34910000000"

    def test_only_mobile_and_no_request_raises_restricted(self):
        supabase, _ = fake_supabase([_verified("+34600111222", is_default=True)])

        with pytest.raises(CallerIdRangeRestricted):
            resolve_caller_id(supabase, "user-1", None, today=ON)

    def test_no_numbers_at_all_is_still_plain_not_verified(self):
        supabase, _ = fake_supabase([])

        with pytest.raises(CallerIdNotVerified) as exc:
            resolve_caller_id(supabase, "user-1", None, today=ON)

        assert not isinstance(exc.value, CallerIdRangeRestricted)

    def test_flag_off_lets_mobile_through_after_the_deadline(self):
        supabase, _ = fake_supabase([_verified("+34600111222", is_default=True)])

        with patch.object(settings, "CALLING_ES_CLI_GATE_ENABLED", False):
            assert (
                resolve_caller_id(supabase, "user-1", "+34600111222", today=ON)
                == "+34600111222"
            )

    def test_block_date_is_configurable(self):
        supabase, _ = fake_supabase([_verified("+34600111222", is_default=True)])

        with patch.object(settings, "CALLING_ES_MOBILE_CALL_BLOCK_FROM", BEFORE):
            with pytest.raises(CallerIdRangeRestricted):
                resolve_caller_id(supabase, "user-1", "+34600111222", today=BEFORE)

    def test_a_400_number_is_never_blocked_at_call_time(self):
        supabase, _ = fake_supabase([_verified("+34400123456", is_default=True)])

        assert resolve_caller_id(supabase, "user-1", None, today=ON) == "+34400123456"

    def test_landline_and_foreign_mobile_resolve_after_the_deadline(self):
        supabase, _ = fake_supabase(
            [_verified("+34910000000"), _verified("+33612345678")]
        )

        assert resolve_caller_id(supabase, "user-1", "+34910000000", today=ON) == "+34910000000"
        assert resolve_caller_id(supabase, "user-1", "+33612345678", today=ON) == "+33612345678"


class TestTwilioVoiceWebhook:
    def _post(self, supabase, today):
        from app.api import webhooks
        from tests.test_telephony_webhook import AUTH_TOKEN, URL, _sign, _test_client

        params = {
            "From": "client:11111111-1111-1111-1111-111111111111",
            "To": "+34910222333",
            "CallerId": "+34600111222",
            "CallSid": "CA00000000000000000000000000000099",
        }
        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            patch("app.services.telephony.caller_id._today_madrid", return_value=today),
            patch.multiple(
                webhooks.settings,
                TWILIO_AUTH_TOKEN=AUTH_TOKEN,
                BACKEND_PUBLIC_URL="https://api.getvocify.com",
                CALLING_RECORDING_ANNOUNCEMENT_ENABLED=False,
            ),
        ):
            return _test_client().post(
                "/webhooks/twilio/voice",
                data=params,
                headers={"X-Twilio-Signature": _sign(URL, params, AUTH_TOKEN)},
            )

    def _stores(self):
        from tests.test_telephony_webhook import _fake_supabase

        return _fake_supabase(
            {
                "user_caller_ids": [
                    _verified(
                        "+34600111222",
                        user="11111111-1111-1111-1111-111111111111",
                        is_default=True,
                    )
                ]
            }
        )

    def test_blocked_mobile_hangs_up_with_a_specific_message(self):
        supabase, stores = self._stores()

        resp = self._post(supabase, ON)

        assert resp.status_code == 200
        assert "<Dial" not in resp.text
        assert "<Hangup" in resp.text
        assert "móvil" in resp.text.lower()
        assert stores.get("outbound_calls", []) == []
        assert stores["user_caller_ids"][0]["status"] == "verified"

    def test_mobile_still_dials_before_the_deadline(self):
        supabase, stores = self._stores()

        resp = self._post(supabase, BEFORE)

        assert 'callerId="+34600111222"' in resp.text
        assert stores["outbound_calls"][0]["from_number"] == "+34600111222"


class TestListing:
    def test_mobile_before_deadline_is_callable_with_a_notice(self):
        supabase, _ = fake_supabase([_verified("+34600111222")])

        [row] = list_caller_ids(supabase, "user-1", today=BEFORE)

        assert row["callBlocked"] is False
        assert "17/10/2026" in row["notice"]

    def test_mobile_from_deadline_is_blocked_with_a_notice(self):
        supabase, _ = fake_supabase([_verified("+34600111222")])

        [row] = list_caller_ids(supabase, "user-1", today=ON)

        assert row["callBlocked"] is True
        assert "móvil" in row["notice"].lower()
        assert row["status"] == "verified"

    def test_landline_has_no_notice(self):
        supabase, _ = fake_supabase([_verified("+34910000000")])

        [row] = list_caller_ids(supabase, "user-1", today=ON)

        assert row["callBlocked"] is False
        assert row["notice"] is None

    def test_flag_off_hides_the_notice(self):
        supabase, _ = fake_supabase([_verified("+34600111222")])

        with patch.object(settings, "CALLING_ES_CLI_GATE_ENABLED", False):
            [row] = list_caller_ids(supabase, "user-1", today=ON)

        assert row["callBlocked"] is False
        assert row["notice"] is None
