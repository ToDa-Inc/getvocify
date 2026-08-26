from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app.api.webhooks import router as webhooks_router
from app.services.telephony.webhook_signature import (
    identity_from_client_from,
    verify_twilio_signature,
)

AUTH_TOKEN = "test-auth-token"
URL = "https://api.getvocify.com/webhooks/twilio/voice"


class TestVerifyTwilioSignature:
    def test_accepts_a_signature_twilio_would_produce(self):
        params = {"To": "+34600111222", "From": "client:user-1"}
        signature = RequestValidator(AUTH_TOKEN).compute_signature(URL, params)
        assert verify_twilio_signature(URL, params, signature, AUTH_TOKEN) is True

    def test_rejects_a_tampered_body(self):
        params = {"To": "+34600111222", "From": "client:user-1"}
        signature = RequestValidator(AUTH_TOKEN).compute_signature(URL, params)
        tampered = {"To": "+34600999999", "From": "client:user-1"}
        assert verify_twilio_signature(URL, tampered, signature, AUTH_TOKEN) is False

    def test_rejects_a_signature_from_a_different_url(self):
        params = {"To": "+34600111222"}
        signature = RequestValidator(AUTH_TOKEN).compute_signature(
            "https://evil.example/webhooks/twilio/voice", params
        )
        assert verify_twilio_signature(URL, params, signature, AUTH_TOKEN) is False

    def test_rejects_empty_signature(self):
        assert verify_twilio_signature(URL, {}, "", AUTH_TOKEN) is False


class TestIdentityFromClientFrom:
    def test_extracts_identity_from_client_prefix(self):
        assert identity_from_client_from("client:abc-123") == "abc-123"

    def test_returns_none_for_a_pstn_from(self):
        assert identity_from_client_from("+34600111222") is None

    def test_returns_none_for_empty(self):
        assert identity_from_client_from("") is None


def _fake_supabase(rows):
    """Minimal supabase-py table().update().eq().execute() chain."""
    store = [dict(r) for r in rows]

    class FakeQuery:
        def __init__(self):
            self._filters: list[tuple[str, object]] = []
            self._mutation: dict | None = None

        def select(self, *_a, **_k):
            return self

        def eq(self, column, value):
            self._filters.append((column, value))
            return self

        def update(self, row):
            self._mutation = row
            return self

        def execute(self):
            matched = [
                r for r in store if all(r.get(c) == v for c, v in self._filters)
            ]
            if self._mutation is not None:
                for r in matched:
                    r.update(self._mutation)
            from types import SimpleNamespace

            return SimpleNamespace(data=matched)

    client = MagicMock()
    client.table.side_effect = lambda _name: FakeQuery()
    return client, store


class TestCallerIdStatusWebhook:
    """`user_caller_ids.twilio_validation_sid` is the only match key.

    Matching on `To` (a bare phone number) instead would flip every row that
    shares that number across every user who ever registered it, so the
    webhook must key off the `CallSid` Twilio includes on every Voice Request
    (the same value persisted as `twilio_validation_sid`) and must not fall
    back to `To`/`PhoneNumber` when it's absent.
    """

    def _client(self):
        app = FastAPI()
        app.include_router(webhooks_router, prefix="/webhooks")
        return TestClient(app)

    def test_callback_with_call_sid_updates_by_sid_not_by_to(self):
        supabase, store = _fake_supabase(
            [
                {
                    "user_id": "user-1",
                    "phone_number": "+34600111222",
                    "status": "pending",
                    "twilio_validation_sid": "CA111",
                },
                {
                    "user_id": "user-2",
                    "phone_number": "+34600111222",
                    "status": "pending",
                    "twilio_validation_sid": "CA222",
                },
            ]
        )
        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            patch.dict("os.environ", {"TWILIO_SKIP_SIG_CHECK": "1"}),
        ):
            resp = self._client().post(
                "/webhooks/twilio/caller-id-status",
                data={
                    "To": "+34600111222",
                    "VerificationStatus": "success",
                    "CallSid": "CA111",
                },
            )

        assert resp.status_code == 204
        assert store[0]["status"] == "verified"
        assert store[1]["status"] == "pending"

    def test_callback_without_call_sid_updates_nothing(self):
        supabase, store = _fake_supabase(
            [
                {
                    "user_id": "user-1",
                    "phone_number": "+34600111222",
                    "status": "pending",
                    "twilio_validation_sid": "CA111",
                }
            ]
        )
        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            patch.dict("os.environ", {"TWILIO_SKIP_SIG_CHECK": "1"}),
        ):
            resp = self._client().post(
                "/webhooks/twilio/caller-id-status",
                data={"To": "+34600111222", "VerificationStatus": "success"},
            )

        assert resp.status_code == 204
        assert store[0]["status"] == "pending"
