from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app.api import webhooks
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


class FakeQuery:
    """Minimal supabase-py table().select/insert/update().eq/order/limit().execute() chain."""

    def __init__(self, store: list[dict]):
        self.store = store
        self._filters: list[tuple[str, object]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._mutation: dict | None = None
        self._mutation_type: str | None = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def order(self, column, desc=False, **_k):
        self._order = (column, desc)
        return self

    def limit(self, n, *_a, **_k):
        self._limit = n
        return self

    def insert(self, row):
        self._mutation_type = "insert"
        self._mutation = row
        return self

    def update(self, row):
        self._mutation_type = "update"
        self._mutation = row
        return self

    def _filtered_rows(self) -> list[dict]:
        rows = list(self.store)
        for column, value in self._filters:
            rows = [r for r in rows if r.get(column) == value]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(
                rows, key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc
            )
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def execute(self):
        if self._mutation_type == "update":
            matched = self._filtered_rows()
            for row in matched:
                row.update(self._mutation or {})
            return SimpleNamespace(data=list(matched))
        if self._mutation_type == "insert":
            row = dict(self._mutation or {})
            self.store.append(row)
            return SimpleNamespace(data=[row])
        return SimpleNamespace(data=self._filtered_rows())


def _fake_supabase(tables: dict[str, list[dict]]):
    """A fake supabase client keyed by table name, e.g. `{"user_caller_ids": [...]}`.

    Tables not listed start empty (so `outbound_calls` inserts can be asserted
    against without pre-seeding). Returns `(client, stores)` where `stores` is
    a `dict[str, list[dict]]` of live table contents.
    """
    stores: dict[str, list[dict]] = {name: [dict(r) for r in rows] for name, rows in tables.items()}

    def make_table(name: str) -> FakeQuery:
        return FakeQuery(stores.setdefault(name, []))

    client = MagicMock()
    client.table.side_effect = make_table
    return client, stores


def _test_client() -> TestClient:
    app = FastAPI()
    app.include_router(webhooks_router, prefix="/webhooks")
    return TestClient(app)


def _sign(url: str, params: dict[str, str], auth_token: str) -> str:
    return RequestValidator(auth_token).compute_signature(url, params)


class TestCallerIdStatusWebhook:
    """`user_caller_ids.twilio_validation_sid` is the only match key.

    Matching on `To` (a bare phone number) instead would flip every row that
    shares that number across every user who ever registered it, so the
    webhook must key off the `CallSid` Twilio includes on every Voice Request
    (the same value persisted as `twilio_validation_sid`) and must not fall
    back to `To`/`PhoneNumber` when it's absent.
    """

    def test_callback_with_call_sid_updates_by_sid_not_by_to(self):
        supabase, stores = _fake_supabase(
            {
                "user_caller_ids": [
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
            }
        )
        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            patch.object(webhooks.settings, "ENVIRONMENT", "development"),
            patch.dict("os.environ", {"TWILIO_SKIP_SIG_CHECK": "1"}),
        ):
            resp = _test_client().post(
                "/webhooks/twilio/caller-id-status",
                data={
                    "To": "+34600111222",
                    "VerificationStatus": "success",
                    "CallSid": "CA111",
                },
            )

        assert resp.status_code == 204
        store = stores["user_caller_ids"]
        assert store[0]["status"] == "verified"
        assert store[1]["status"] == "pending"

    def test_callback_without_call_sid_updates_nothing(self):
        supabase, stores = _fake_supabase(
            {
                "user_caller_ids": [
                    {
                        "user_id": "user-1",
                        "phone_number": "+34600111222",
                        "status": "pending",
                        "twilio_validation_sid": "CA111",
                    }
                ]
            }
        )
        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            patch.object(webhooks.settings, "ENVIRONMENT", "development"),
            patch.dict("os.environ", {"TWILIO_SKIP_SIG_CHECK": "1"}),
        ):
            resp = _test_client().post(
                "/webhooks/twilio/caller-id-status",
                data={"To": "+34600111222", "VerificationStatus": "success"},
            )

        assert resp.status_code == 204
        assert stores["user_caller_ids"][0]["status"] == "pending"


class TestTwilioSkipSigCheckProductionGate:
    """`TWILIO_SKIP_SIG_CHECK` must be impossible in production.

    A misconfigured prod deploy that still carries the dev escape hatch in its
    environment must fail closed (403), not silently accept unsigned requests.
    """

    def test_skip_flag_is_refused_in_production(self):
        with (
            patch.object(webhooks.settings, "ENVIRONMENT", "production"),
            patch.object(webhooks.settings, "TWILIO_AUTH_TOKEN", AUTH_TOKEN),
            patch.dict("os.environ", {"TWILIO_SKIP_SIG_CHECK": "1"}),
        ):
            resp = _test_client().post(
                "/webhooks/twilio/whisper", data={"CallSid": "CA1"}
            )

        assert resp.status_code == 403

    def test_skip_flag_still_works_outside_production(self):
        with (
            patch.object(webhooks.settings, "ENVIRONMENT", "development"),
            patch.dict("os.environ", {"TWILIO_SKIP_SIG_CHECK": "1"}),
        ):
            resp = _test_client().post(
                "/webhooks/twilio/whisper", data={"CallSid": "CA1"}
            )

        assert resp.status_code == 200


class TestVoiceRouteSignature:
    """Route-level tests exercising the real Twilio signature path.

    Every test here computes a genuine (or deliberately wrong) signature with
    `RequestValidator`, the way Twilio itself would, rather than relying on
    `TWILIO_SKIP_SIG_CHECK` — that flag is covered separately and must not
    substitute for testing the actual security boundary.
    """

    URL = "https://api.getvocify.com/webhooks/twilio/voice"
    WHISPER_URL = "https://api.getvocify.com/webhooks/twilio/whisper"

    def _patched_settings(self):
        return patch.multiple(
            webhooks.settings,
            TWILIO_AUTH_TOKEN=AUTH_TOKEN,
            BACKEND_PUBLIC_URL="https://api.getvocify.com",
        )

    def test_valid_signature_dials_using_the_caller_id_resolved_from_the_db(self):
        user_id = "11111111-1111-1111-1111-111111111111"
        params = {
            "From": f"client:{user_id}",
            "To": "+34600111222",
            "CallSid": "CA00000000000000000000000000000001",
        }
        signature = _sign(self.URL, params, AUTH_TOKEN)
        supabase, stores = _fake_supabase(
            {
                "user_caller_ids": [
                    {
                        "user_id": user_id,
                        "phone_number": "+34910000000",
                        "status": "verified",
                        "is_default": True,
                    }
                ]
            }
        )

        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            self._patched_settings(),
        ):
            resp = _test_client().post(
                "/webhooks/twilio/voice",
                data=params,
                headers={"X-Twilio-Signature": signature},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/xml")
        # The client never sent a CallerId at all — the number in the TwiML
        # comes solely from the DB lookup, never from client-supplied input.
        assert 'record="record-from-answer-dual"' in resp.text
        assert 'callerId="+34910000000"' in resp.text
        assert stores["outbound_calls"][0]["from_number"] == "+34910000000"

    def test_client_requesting_an_unverified_caller_id_is_rejected_not_dialed(self):
        """The security boundary: a client-supplied CallerId is a preference,
        never an authorization. Requesting a number this user hasn't verified
        — here, one verified for a *different* user — must reject, not dial.
        """
        user_id = "22222222-2222-2222-2222-222222222222"
        other_user_id = "33333333-3333-3333-3333-333333333333"
        spoofed_number = "+34699999999"
        params = {
            "From": f"client:{user_id}",
            "To": "+34600111222",
            "CallerId": spoofed_number,
            "CallSid": "CA00000000000000000000000000000002",
        }
        signature = _sign(self.URL, params, AUTH_TOKEN)
        supabase, stores = _fake_supabase(
            {
                "user_caller_ids": [
                    {
                        "user_id": other_user_id,
                        "phone_number": spoofed_number,
                        "status": "verified",
                    }
                ]
            }
        )

        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            self._patched_settings(),
        ):
            resp = _test_client().post(
                "/webhooks/twilio/voice",
                data=params,
                headers={"X-Twilio-Signature": signature},
            )

        assert resp.status_code == 200
        assert "<Hangup" in resp.text
        assert "<Dial" not in resp.text
        assert stores.get("outbound_calls", []) == []

    def test_invalid_signature_is_rejected_with_no_db_write(self):
        user_id = "44444444-4444-4444-4444-444444444444"
        params = {
            "From": f"client:{user_id}",
            "To": "+34600111222",
            "CallSid": "CA00000000000000000000000000000003",
        }
        supabase, stores = _fake_supabase(
            {
                "user_caller_ids": [
                    {
                        "user_id": user_id,
                        "phone_number": "+34910000000",
                        "status": "verified",
                        "is_default": True,
                    }
                ]
            }
        )

        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            self._patched_settings(),
        ):
            resp = _test_client().post(
                "/webhooks/twilio/voice",
                data=params,
                headers={"X-Twilio-Signature": "not-a-real-signature"},
            )

        assert resp.status_code == 403
        assert stores.get("outbound_calls", []) == []

    def test_missing_call_sid_is_rejected_even_with_a_valid_signature(self):
        """A genuine Twilio Voice Request always carries a CallSid. Without
        one, inserting `""` would violate outbound_calls' NOT NULL UNIQUE
        constraint on the first request and get silently swallowed as a
        duplicate on every one after — so this must reject before the insert.
        """
        user_id = "55555555-5555-5555-5555-555555555555"
        params = {
            "From": f"client:{user_id}",
            "To": "+34600111222",
        }
        signature = _sign(self.URL, params, AUTH_TOKEN)
        supabase, stores = _fake_supabase(
            {
                "user_caller_ids": [
                    {
                        "user_id": user_id,
                        "phone_number": "+34910000000",
                        "status": "verified",
                        "is_default": True,
                    }
                ]
            }
        )

        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            self._patched_settings(),
        ):
            resp = _test_client().post(
                "/webhooks/twilio/voice",
                data=params,
                headers={"X-Twilio-Signature": signature},
            )

        assert resp.status_code == 200
        assert "<Hangup" in resp.text
        assert stores.get("outbound_calls", []) == []

    def test_hub_id_from_the_request_never_reaches_the_inserted_row(self):
        """`hubspot_hub_id` is the authorization comparison in the public
        recording endpoint HubSpot calls; a client-supplied value would taint
        it. Task 6 must populate it from the user's own `crm_connections` row.
        """
        user_id = "66666666-6666-6666-6666-666666666666"
        params = {
            "From": f"client:{user_id}",
            "To": "+34600111222",
            "CallSid": "CA00000000000000000000000000000004",
            "HubId": "999999",
            "ContactId": "123",
            "DealId": "456",
        }
        signature = _sign(self.URL, params, AUTH_TOKEN)
        supabase, stores = _fake_supabase(
            {
                "user_caller_ids": [
                    {
                        "user_id": user_id,
                        "phone_number": "+34910000000",
                        "status": "verified",
                        "is_default": True,
                    }
                ]
            }
        )

        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            self._patched_settings(),
        ):
            resp = _test_client().post(
                "/webhooks/twilio/voice",
                data=params,
                headers={"X-Twilio-Signature": signature},
            )

        assert resp.status_code == 200
        row = stores["outbound_calls"][0]
        assert row["hubspot_hub_id"] is None
        assert row["hubspot_contact_id"] == "123"
        assert row["hubspot_deal_id"] == "456"

    def test_whisper_route_rejects_an_invalid_signature(self):
        with self._patched_settings():
            resp = _test_client().post(
                "/webhooks/twilio/whisper",
                data={"CallSid": "CA1"},
                headers={"X-Twilio-Signature": "not-a-real-signature"},
            )

        assert resp.status_code == 403
