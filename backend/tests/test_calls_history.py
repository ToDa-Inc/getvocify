from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.calls import get_call, list_call_history


class FakeQuery:
    def __init__(self, store: list[dict]):
        self.store = store
        self._filters: list[tuple[str, object]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def in_(self, column, values):
        self._in_filters.append((column, list(values)))
        return self

    def order(self, column, desc=False, **_k):
        self._order = (column, desc)
        return self

    def limit(self, n, *_a, **_k):
        self._limit = n
        return self

    def execute(self):
        rows = list(self.store)
        for column, value in self._filters:
            rows = [r for r in rows if r.get(column) == value]
        for column, values in self._in_filters:
            allowed = set(values)
            rows = [r for r in rows if r.get(column) in allowed]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(
                rows,
                key=lambda r: (r.get(column) is None, r.get(column)),
                reverse=desc,
            )
        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows)


def fake_db(tables: dict[str, list[dict]]):
    stores = {name: [dict(r) for r in rows] for name, rows in tables.items()}

    def make_table(name: str):
        return FakeQuery(stores.setdefault(name, []))

    client = MagicMock()
    client.table.side_effect = make_table
    return client, stores


CALL_A = {
    "user_id": "user-1",
    "twilio_call_sid": "CA1",
    "to_number": "+34600111222",
    "from_number": "+34910000000",
    "hubspot_contact_id": "C1",
    "hubspot_deal_id": "D1",
    "hubspot_engagement_id": "E1",
    "status": "logged",
    "created_at": "2026-09-01T10:00:00Z",
    "answered_at": "2026-09-01T10:00:05Z",
    "recording_duration": 42,
    "memo_id": "memo-1",
    "error_message": None,
}
CALL_B = {
    "user_id": "user-1",
    "twilio_call_sid": "CA2",
    "to_number": "+34600999999",
    "from_number": "+34910000000",
    "hubspot_contact_id": "C2",
    "hubspot_deal_id": None,
    "hubspot_engagement_id": None,
    "status": "dialing",
    "created_at": "2026-09-01T11:00:00Z",
    "answered_at": None,
    "recording_duration": None,
    "memo_id": None,
    "error_message": None,
}
CALL_OTHER_USER = {
    **CALL_A,
    "user_id": "user-2",
    "twilio_call_sid": "CA-other",
    "memo_id": "memo-secret",
}


@pytest.mark.asyncio
async def test_history_is_scoped_to_the_user():
    supabase, _ = fake_db(
        {
            "outbound_calls": [CALL_A, CALL_OTHER_USER, CALL_B],
            "memos": [{"id": "memo-1", "status": "pending_review"}],
        }
    )
    result = await list_call_history(
        limit=20, contactId=None, dealId=None, supabase=supabase, user_id="user-1"
    )
    sids = [c["callSid"] for c in result["calls"]]
    assert sids == ["CA2", "CA1"]
    assert result["calls"][1]["memoStatus"] == "pending_review"
    assert result["calls"][0]["memoStatus"] is None


@pytest.mark.asyncio
async def test_history_limit_is_clamped_by_query():
    rows = [
        {**CALL_B, "twilio_call_sid": f"CA{i}", "created_at": f"2026-09-01T{i:02d}:00:00Z"}
        for i in range(5)
    ]
    supabase, _ = fake_db({"outbound_calls": rows, "memos": []})
    result = await list_call_history(
        limit=2, contactId=None, dealId=None, supabase=supabase, user_id="user-1"
    )
    assert len(result["calls"]) == 2


@pytest.mark.asyncio
async def test_history_filters_compose():
    supabase, _ = fake_db({"outbound_calls": [CALL_A, CALL_B], "memos": []})
    result = await list_call_history(
        limit=20, contactId="C1", dealId="D1", supabase=supabase, user_id="user-1"
    )
    assert [c["callSid"] for c in result["calls"]] == ["CA1"]


@pytest.mark.asyncio
async def test_get_call_unknown_is_404():
    supabase, _ = fake_db({"outbound_calls": [CALL_A], "memos": []})
    with pytest.raises(HTTPException) as exc:
        await get_call("CA-missing", supabase=supabase, user_id="user-1")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_call_other_user_is_404_not_403():
    supabase, _ = fake_db({"outbound_calls": [CALL_OTHER_USER], "memos": []})
    with pytest.raises(HTTPException) as exc:
        await get_call("CA-other", supabase=supabase, user_id="user-1")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_call_returns_summary():
    supabase, _ = fake_db(
        {
            "outbound_calls": [CALL_A],
            "memos": [{"id": "memo-1", "status": "approved"}],
        }
    )
    result = await get_call("CA1", supabase=supabase, user_id="user-1")
    assert result["callSid"] == "CA1"
    assert result["to"] == "+34600111222"
    assert result["from"] == "+34910000000"
    assert result["memoStatus"] == "approved"
    assert result["durationSeconds"] == 42
