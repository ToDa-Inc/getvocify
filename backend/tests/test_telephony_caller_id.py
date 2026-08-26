from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.telephony.caller_id import (
    CallerIdNotVerified,
    resolve_caller_id,
    start_caller_id_verification,
)


class FakeQuery:
    """Minimal supabase-py table() chain returning a canned payload."""

    def __init__(self, rows):
        self.rows = rows
        self.inserted = None
        self.updated = None

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def insert(self, row):
        self.inserted = row
        return self

    def upsert(self, row, **_k):
        self.inserted = row
        return self

    def update(self, row):
        self.updated = row
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


def fake_supabase(rows):
    query = FakeQuery(rows)
    client = MagicMock()
    client.table.return_value = query
    return client, query


class TestResolveCallerId:
    def test_returns_requested_number_when_verified_for_that_user(self):
        supabase, _ = fake_supabase(
            [{"phone_number": "+34910000000", "status": "verified"}]
        )
        assert (
            resolve_caller_id(supabase, "user-1", "+34910000000") == "+34910000000"
        )

    def test_rejects_number_that_is_not_verified(self):
        supabase, _ = fake_supabase([])
        with pytest.raises(CallerIdNotVerified):
            resolve_caller_id(supabase, "user-1", "+34910000000")

    def test_rejects_number_still_pending(self):
        supabase, _ = fake_supabase(
            [{"phone_number": "+34910000000", "status": "pending"}]
        )
        with pytest.raises(CallerIdNotVerified):
            resolve_caller_id(supabase, "user-1", "+34910000000")

    def test_falls_back_to_default_when_no_number_requested(self):
        supabase, _ = fake_supabase(
            [{"phone_number": "+34910000001", "status": "verified"}]
        )
        assert resolve_caller_id(supabase, "user-1", None) == "+34910000001"

    def test_raises_when_user_has_no_verified_number_at_all(self):
        supabase, _ = fake_supabase([])
        with pytest.raises(CallerIdNotVerified):
            resolve_caller_id(supabase, "user-1", None)


class TestStartCallerIdVerification:
    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_normalizes_number_and_returns_twilio_code(self, rest):
        rest.return_value.validation_requests.create.return_value = SimpleNamespace(
            validation_code="482913", friendly_name="Oficina"
        )
        supabase, query = fake_supabase([{"id": "row-1"}])

        result = start_caller_id_verification(
            supabase, "user-1", "600 111 222", label="Oficina"
        )

        assert result["phoneNumber"] == "+34600111222"
        assert result["verificationCode"] == "482913"
        assert result["status"] == "pending"
        assert query.inserted["phone_number"] == "+34600111222"
        assert query.inserted["status"] == "pending"

    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_passes_status_callback_to_twilio(self, rest):
        rest.return_value.validation_requests.create.return_value = SimpleNamespace(
            validation_code="111111", friendly_name=None
        )
        supabase, _ = fake_supabase([{"id": "row-1"}])

        start_caller_id_verification(supabase, "user-1", "+34600111222", label=None)

        kwargs = rest.return_value.validation_requests.create.call_args.kwargs
        assert "webhooks/twilio/caller-id-status" in kwargs["status_callback"]
        assert kwargs["phone_number"] == "+34600111222"
