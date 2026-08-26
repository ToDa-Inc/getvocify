from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.telephony.caller_id import (
    CallerIdNotVerified,
    mark_caller_id_verified,
    resolve_caller_id,
    start_caller_id_verification,
)


class FakeQuery:
    """Minimal supabase-py table() chain with working eq/order/limit filters."""

    def __init__(self, store: list[dict]):
        self.store = store
        self._filters: list[tuple[str, object]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._mutation: dict | None = None
        self._mutation_type: str | None = None
        self.inserted = None
        self.updated = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, n, *_a, **_k):
        self._limit = n
        return self

    def order(self, column, desc=False, **_k):
        self._order = (column, desc)
        return self

    def insert(self, row):
        self._mutation_type = "insert"
        self._mutation = row
        self.inserted = row
        return self

    def upsert(self, row, **_k):
        self._mutation_type = "upsert"
        self._mutation = row
        self.inserted = row
        return self

    def update(self, row):
        self._mutation_type = "update"
        self._mutation = row
        self.updated = row
        return self

    def _filtered_rows(self) -> list[dict]:
        rows = list(self.store)
        for column, value in self._filters:
            rows = [r for r in rows if r.get(column) == value]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(
                rows,
                key=lambda r: (r.get(column) is None, r.get(column)),
                reverse=desc,
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
        if self._mutation_type == "upsert":
            row = dict(self._mutation or {})
            for existing in self.store:
                if (
                    existing.get("user_id") == row.get("user_id")
                    and existing.get("phone_number") == row.get("phone_number")
                ):
                    for key, value in row.items():
                        if key == "label" and value is None:
                            continue
                        existing[key] = value
                    return SimpleNamespace(data=[existing])
            self.store.append(row)
            return SimpleNamespace(data=[row])
        if self._mutation_type == "insert":
            row = dict(self._mutation or {})
            self.store.append(row)
            return SimpleNamespace(data=[row])
        return SimpleNamespace(data=self._filtered_rows())


def fake_supabase(rows):
    store = [dict(r) for r in rows]

    def make_query(_name):
        return FakeQuery(store)

    client = MagicMock()
    client.table.side_effect = make_query
    return client, store


class TestResolveCallerId:
    def test_returns_requested_number_when_verified_for_that_user(self):
        supabase, store = fake_supabase(
            [
                {
                    "user_id": "user-1",
                    "phone_number": "+34910000000",
                    "status": "verified",
                }
            ]
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
            [
                {
                    "user_id": "user-1",
                    "phone_number": "+34910000000",
                    "status": "pending",
                }
            ]
        )
        with pytest.raises(CallerIdNotVerified):
            resolve_caller_id(supabase, "user-1", "+34910000000")

    def test_rejects_verified_number_belonging_to_different_user(self):
        supabase, _ = fake_supabase(
            [
                {
                    "user_id": "user-2",
                    "phone_number": "+34910000000",
                    "status": "verified",
                }
            ]
        )
        with pytest.raises(CallerIdNotVerified):
            resolve_caller_id(supabase, "user-1", "+34910000000")

    def test_falls_back_to_default_when_no_number_requested(self):
        supabase, _ = fake_supabase(
            [
                {
                    "user_id": "user-1",
                    "phone_number": "+34910000000",
                    "status": "verified",
                    "is_default": False,
                },
                {
                    "user_id": "user-1",
                    "phone_number": "+34910000001",
                    "status": "verified",
                    "is_default": True,
                },
            ]
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
            validation_code="482913",
            friendly_name="Oficina",
            call_sid="CAabc123",
        )
        supabase, store = fake_supabase([])

        result = start_caller_id_verification(
            supabase, "user-1", "600 111 222", label="Oficina"
        )

        assert result["phoneNumber"] == "+34600111222"
        assert result["verificationCode"] == "482913"
        assert result["status"] == "pending"
        assert result["validationSid"] == "CAabc123"
        assert result["alreadyVerified"] is False
        assert store[0]["phone_number"] == "+34600111222"
        assert store[0]["status"] == "pending"
        assert store[0]["twilio_validation_sid"] == "CAabc123"

    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_passes_status_callback_to_twilio(self, rest):
        rest.return_value.validation_requests.create.return_value = SimpleNamespace(
            validation_code="111111",
            friendly_name=None,
            call_sid="CAxyz789",
        )
        supabase, _ = fake_supabase([])

        start_caller_id_verification(supabase, "user-1", "+34600111222", label=None)

        kwargs = rest.return_value.validation_requests.create.call_args.kwargs
        assert "webhooks/twilio/caller-id-status" in kwargs["status_callback"]
        assert kwargs["phone_number"] == "+34600111222"

    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_skips_twilio_when_already_verified(self, rest):
        supabase, store = fake_supabase(
            [
                {
                    "user_id": "user-1",
                    "phone_number": "+34600111222",
                    "status": "verified",
                    "label": "Oficina",
                    "twilio_validation_sid": "CA-old",
                    "verified_at": "2026-01-01T00:00:00Z",
                }
            ]
        )

        result = start_caller_id_verification(
            supabase, "user-1", "+34600111222", label=None
        )

        rest.assert_not_called()
        assert result == {
            "phoneNumber": "+34600111222",
            "status": "verified",
            "validationSid": "CA-old",
            "alreadyVerified": True,
        }
        assert store[0]["status"] == "verified"

    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_does_not_clobber_label_with_none_on_reverification(self, rest):
        rest.return_value.validation_requests.create.return_value = SimpleNamespace(
            validation_code="999999",
            friendly_name=None,
            call_sid="CA-new",
        )
        supabase, store = fake_supabase(
            [
                {
                    "user_id": "user-1",
                    "phone_number": "+34600111222",
                    "status": "failed",
                    "label": "Oficina",
                }
            ]
        )

        start_caller_id_verification(supabase, "user-1", "+34600111222", label=None)

        assert store[0]["label"] == "Oficina"


class TestMarkCallerIdVerified:
    def test_verification_callback_updates_only_matching_validation_sid(self):
        supabase, store = fake_supabase(
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

        assert mark_caller_id_verified(supabase, "CA111") is True
        assert store[0]["status"] == "verified"
        assert store[1]["status"] == "pending"

    def test_returns_false_when_validation_sid_is_missing(self):
        supabase, store = fake_supabase(
            [
                {
                    "user_id": "user-1",
                    "phone_number": "+34600111222",
                    "status": "pending",
                    "twilio_validation_sid": "CA111",
                }
            ]
        )

        assert mark_caller_id_verified(supabase, None) is False
        assert mark_caller_id_verified(supabase, "") is False
        assert store[0]["status"] == "pending"
