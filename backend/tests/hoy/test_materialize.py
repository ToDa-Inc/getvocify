from datetime import datetime, timedelta, timezone

from app.services.hoy.materialize import (
    callback_no_answer_from_calls,
    contact_last_touch_at,
    exclude_handoff_contacts,
    fresh_signals,
    never_contacted_signals,
    refresh_hoy_signals,
    retracted_call_callback_ids,
    retracted_callback_ids,
    retracted_objection_ids,
)
from app.services.hoy.signals import Signal


NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
DAY_END = datetime(2026, 9, 24, 21, 59, tzinfo=timezone.utc)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """Minimal fake: chained .eq()/.select() filters an in-memory table; .update()/.upsert()
    mutate it; enough for refresh_hoy_signals, nothing more."""

    def __init__(self, table: "_FakeSupabase", name: str):
        self._table = table
        self._name = name
        self._filters: list[tuple[str, object]] = []
        self._patch: dict | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def or_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def update(self, patch):
        self._patch = dict(patch)
        return self

    def in_(self, column, values):
        self._filters.append((f"in:{column}", set(values)))
        return self

    def upsert(self, row, on_conflict=None):
        stored = dict(row)
        stored.setdefault("id", f"gen-{len(self._table.rows(self._name)) + 1}")
        self._table.rows(self._name).append(stored)
        return self

    def _matching(self):
        rows = self._table.rows(self._name)
        for column, value in self._filters:
            if column.startswith("in:"):
                key = column[3:]
                rows = [row for row in rows if row.get(key) in value]
            else:
                rows = [row for row in rows if row.get(column) == value]
        return rows

    def execute(self):
        if self._patch is not None:
            for row in self._matching():
                row.update(self._patch)
            return _Result(None)
        return _Result(list(self._matching()))


class _FakeSupabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = {name: list(rows) for name, rows in tables.items()}

    def rows(self, name: str) -> list[dict]:
        return self._tables.setdefault(name, [])

    def table(self, name: str) -> _Query:
        return _Query(self, name)


def test_a_stored_open_objection_becomes_one_signal_without_a_model():
    signals = fresh_signals(
        [{
            "id": "memo-1",
            "hubspot_contact_id": "42",
            "capture_started_at": "2026-09-20T10:00:00Z",
            "extraction": {
                "intelligence": {
                    "interest": "high",
                    "objections": [{"resolution": "open", "category": "price", "quote": "Está caro"}],
                }
            },
        }],
        now=NOW,
        day_end=DAY_END,
    )
    assert [signal.type for signal in signals] == ["objection_open"]
    assert signals[0].payload["category"] == "price"
    assert "caro" in signals[0].payload["quote"]


def _memo_with_empty_c04():
    return {
        "id": "memo-1",
        "hubspot_contact_id": "42",
        "capture_started_at": "2026-09-20T10:00:00Z",
        "extraction": {
            "objections": ["No es el mejor momento"],
            "intelligence": {"interest": "high", "objections": []},
        },
    }


def test_current_intelligence_with_no_objections_overrides_the_legacy_text(monkeypatch):
    monkeypatch.setattr("app.services.intelligence.extract.is_current", lambda _memo: True)
    signals = fresh_signals([_memo_with_empty_c04()], now=NOW, day_end=DAY_END)
    assert "objection_open" not in [signal.type for signal in signals]


def test_stale_intelligence_with_no_objections_keeps_the_legacy_text(monkeypatch):
    monkeypatch.setattr("app.services.intelligence.extract.is_current", lambda _memo: False)
    signals = fresh_signals([_memo_with_empty_c04()], now=NOW, day_end=DAY_END)
    assert "objection_open" in [signal.type for signal in signals]


def test_only_a_pending_objection_of_a_reread_memo_is_retracted():
    existing = [
        {"id": "a", "type": "objection_open", "status": "pending", "memo_id": "memo-1", "dedupe_key": "objection:memo-1:other"},
        {"id": "b", "type": "objection_open", "status": "pending", "memo_id": "memo-1", "dedupe_key": "objection:memo-1:price"},
        {"id": "c", "type": "objection_open", "status": "pending", "memo_id": "memo-old", "dedupe_key": "objection:memo-old:other"},
        {"id": "d", "type": "objection_open", "status": "done", "memo_id": "memo-1", "dedupe_key": "objection:memo-1:timing"},
        {"id": "e", "type": "going_cold", "status": "pending", "memo_id": "memo-1", "dedupe_key": "cold:42"},
    ]
    kept = {"objection:memo-1:price"}
    assert retracted_objection_ids(existing, memo_ids={"memo-1"}, fresh_keys=kept) == ["a"]


# --- T5: HOY_LEAD_TIERS_ENABLED wiring through fresh_signals ---


def _no_answer_memo(days_ago: int) -> dict:
    return {
        "id": "memo-na",
        "hubspot_contact_id": "42",
        "capture_started_at": (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z"),
        "extraction": {},
        "screening_outcome": "no_response",
    }


def test_flag_off_never_produces_callback_no_answer_even_past_the_default_threshold():
    signals = fresh_signals([_no_answer_memo(5)], now=NOW, day_end=DAY_END, lead_tiers_enabled=False)
    assert signals == []


def test_flag_on_produces_callback_no_answer_after_the_configured_days():
    signals = fresh_signals(
        [_no_answer_memo(3)], now=NOW, day_end=DAY_END, lead_tiers_enabled=True, callback_after_days=2,
    )
    assert [signal.type for signal in signals] == ["callback_no_answer"]
    assert datetime.fromisoformat(signals[0].payload["at"]) == NOW - timedelta(days=3)


def test_flag_on_attaches_heat_to_the_signal_payload_flag_off_does_not():
    memo = {
        "id": "memo-hot",
        "hubspot_contact_id": "42",
        "capture_started_at": (NOW - timedelta(days=12)).isoformat().replace("+00:00", "Z"),
        "extraction": {"intelligence": {"interest": "high"}},
    }
    off = fresh_signals([memo], now=NOW, day_end=DAY_END, lead_tiers_enabled=False)
    assert "heat" not in off[0].payload
    on = fresh_signals([memo], now=NOW, day_end=DAY_END, lead_tiers_enabled=True)
    assert isinstance(on[0].payload["heat"], int)
    assert on[0].payload["heat"] > 0


def test_never_contacted_signals_trusts_rank_candidates_never_called_flag():
    """T5 review: reuses rank_candidates's own never_called (contacted False, per-row
    complete coverage, owner_ambiguous/meeting/closed-deal already excluded there)."""
    candidates = [
        {"contact_id": "1", "connection_id": "crm-A", "never_called": True},
        {"contact_id": "2", "connection_id": "crm-A", "never_called": False},
        {"contact_id": "3", "connection_id": "crm-A", "never_called": True},
    ]
    kept = never_contacted_signals(candidates, touched_contact_ids={"3"})
    assert [signal.contact_id for signal in kept] == ["1"]
    assert kept[0].type == "never_contacted"


def test_never_contacted_signals_caps_at_the_given_limit():
    candidates = [{"contact_id": str(i), "connection_id": "crm-A", "never_called": True} for i in range(10)]
    kept = never_contacted_signals(candidates, touched_contact_ids=set(), limit=3)
    assert len(kept) == 3


def test_exclude_handoff_contacts_drops_only_those_contacts():
    signals = [
        Signal(type="going_cold", contact_id="1", deal_id=None, source_memo_id="m", due_at=None, payload={}, dedupe_key="a"),
        Signal(type="going_cold", contact_id="2", deal_id=None, source_memo_id="m", due_at=None, payload={}, dedupe_key="b"),
    ]
    kept = exclude_handoff_contacts(signals, {"1"})
    assert [signal.contact_id for signal in kept] == ["2"]
    assert exclude_handoff_contacts(signals, set()) == signals


# --- T5 review: callback_no_answer from outbound_calls (missed calls never get a memo) ---


def test_contact_last_touch_at_takes_the_newest_memo_per_contact():
    memos = [
        {"hubspot_contact_id": "1", "capture_started_at": (NOW - timedelta(days=5)).isoformat()},
        {"hubspot_contact_id": "1", "capture_started_at": (NOW - timedelta(days=1)).isoformat()},
        {"hubspot_contact_id": "2", "capture_started_at": (NOW - timedelta(days=3)).isoformat()},
    ]
    latest = contact_last_touch_at(memos)
    assert latest["1"] == NOW - timedelta(days=1)
    assert latest["2"] == NOW - timedelta(days=3)


def _call(contact_id: str, days_ago: int, disposition: str, call_id: str = "call-1") -> dict:
    return {
        "id": call_id,
        "user_id": "user-a",
        "hubspot_contact_id": contact_id,
        "hubspot_deal_id": None,
        "call_disposition": disposition,
        "created_at": (NOW - timedelta(days=days_ago)).isoformat(),
    }


def test_callback_no_answer_from_calls_needs_the_threshold_and_no_later_touch():
    too_soon = callback_no_answer_from_calls(
        [_call("1", 1, "no_answer")], last_touch_at={}, now=NOW, callback_after_days=2,
    )
    assert too_soon == []

    overdue = callback_no_answer_from_calls(
        [_call("1", 3, "busy")], last_touch_at={}, now=NOW, callback_after_days=2,
    )
    assert [signal.type for signal in overdue] == ["callback_no_answer"]
    assert overdue[0].dedupe_key == "callback:call:call-1"

    superseded = callback_no_answer_from_calls(
        [_call("1", 3, "voicemail")], last_touch_at={"1": NOW - timedelta(days=1)}, now=NOW, callback_after_days=2,
    )
    assert superseded == []

    connected_ignored = callback_no_answer_from_calls(
        [_call("1", 3, "connected")], last_touch_at={}, now=NOW, callback_after_days=2,
    )
    assert connected_ignored == []


def test_callback_no_answer_from_calls_keeps_only_the_latest_attempt_per_contact():
    calls = [
        _call("1", 10, "no_answer", call_id="call-old"),
        _call("1", 3, "no_answer", call_id="call-new"),
    ]
    out = callback_no_answer_from_calls(calls, last_touch_at={}, now=NOW, callback_after_days=2)
    assert [s.dedupe_key for s in out] == ["callback:call:call-new"]


# --- T5 review: refresh_hoy_signals retracts stale pending callback_no_answer rows ---


def test_refresh_hoy_signals_retracts_a_memo_based_callback_after_a_later_connected_call():
    """BLOCKING fix: a pending callback_no_answer must resolve once the same contact's
    memo window shows a later connected conversation - the same way a resolved objection
    already does."""
    supabase = _FakeSupabase({
        "memos": [
            {
                "id": "memo-1",
                "user_id": "user-a",
                "hubspot_contact_id": "42",
                "capture_started_at": (NOW - timedelta(days=5)).isoformat(),
                "created_at": (NOW - timedelta(days=5)).isoformat(),
                "extraction": {},
                "screening_outcome": "no_response",
            },
            {
                "id": "memo-2",
                "user_id": "user-a",
                "hubspot_contact_id": "42",
                "capture_started_at": (NOW - timedelta(days=1)).isoformat(),
                "created_at": (NOW - timedelta(days=1)).isoformat(),
                "extraction": {"intelligence": {"interest": "high"}},
                "screening_outcome": "connected",
            },
        ],
        "action_signals": [{
            "id": "row-1",
            "company_id": "co-1",
            "user_id": "user-a",
            "type": "callback_no_answer",
            "status": "pending",
            "memo_id": "memo-1",
            "dedupe_key": "callback:memo-1",
        }],
    })
    refresh_hoy_signals(
        supabase,
        company_id="co-1",
        user_id="user-a",
        now=NOW,
        tz_name="Europe/Madrid",
        lead_tiers_enabled=True,
        callback_after_days=2,
    )
    row = next(row for row in supabase.rows("action_signals") if row["id"] == "row-1")
    assert row["status"] == "resolved"


def test_refresh_hoy_signals_writes_a_call_based_callback_and_retracts_it_once_superseded():
    supabase = _FakeSupabase({
        "memos": [],
        "action_signals": [],
        "outbound_calls": [_call("42", 3, "no_answer", call_id="call-1")],
    })
    refresh_hoy_signals(
        supabase,
        company_id="co-1",
        user_id="user-a",
        now=NOW,
        tz_name="Europe/Madrid",
        lead_tiers_enabled=True,
        callback_after_days=2,
    )
    written = [row for row in supabase.rows("action_signals") if row["dedupe_key"] == "callback:call:call-1"]
    assert len(written) == 1
    assert written[0]["status"] == "pending"

    # A later connected memo for the same contact supersedes the missed-call card.
    supabase.rows("memos").append({
        "id": "memo-connected",
        "user_id": "user-a",
        "hubspot_contact_id": "42",
        "capture_started_at": NOW.isoformat(),
        "created_at": NOW.isoformat(),
        "extraction": {"intelligence": {"interest": "high"}},
        "screening_outcome": "connected",
    })
    refresh_hoy_signals(
        supabase,
        company_id="co-1",
        user_id="user-a",
        now=NOW,
        tz_name="Europe/Madrid",
        lead_tiers_enabled=True,
        callback_after_days=2,
    )
    row = next(row for row in supabase.rows("action_signals") if row["dedupe_key"] == "callback:call:call-1")
    assert row["status"] == "resolved"
