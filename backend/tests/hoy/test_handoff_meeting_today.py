"""An SDR-booked meeting reaches the AE as a "Reunión hoy" card on the day (Lista 3 fix)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.meetings.today import (
    HANDOFF_KEY_PREFIX,
    MEETING_TYPE,
    handoff_meeting_signal,
    refresh_meeting_today,
)

NOW = datetime(2026, 9, 29, 7, 0, tzinfo=timezone.utc)  # 09:00 in Madrid


def _handoff(**overrides) -> dict:
    row = {
        "id": "h-1", "company_id": "co-1", "connection_id": "crm-A", "contact_id": "42",
        "deal_id": "d1", "sdr_user_id": "sdr-1", "ae_user_id": "ae-1", "status": "active",
        "source_memo_id": "memo-sdr", "meeting_starts_at": "2026-09-29T09:00:00+00:00",
        "created_at": "2026-09-27T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def test_a_handoff_meeting_today_is_a_card():
    signal = handoff_meeting_signal(_handoff(), now=NOW, tz_name="Europe/Madrid")
    assert signal is not None
    assert signal.type == MEETING_TYPE
    assert signal.contact_id == "42"
    assert signal.dedupe_key == f"{HANDOFF_KEY_PREFIX}h-1"
    assert signal.payload["starts_at"] == "2026-09-29T09:00:00+00:00"
    assert signal.payload["sdr_user_id"] == "sdr-1"


def test_no_card_on_another_day_without_a_time_or_once_closed():
    assert handoff_meeting_signal(_handoff(meeting_starts_at="2026-09-30T09:00:00+00:00"), now=NOW, tz_name="Europe/Madrid") is None
    assert handoff_meeting_signal(_handoff(meeting_starts_at=None), now=NOW, tz_name="Europe/Madrid") is None
    assert handoff_meeting_signal(_handoff(status="closed"), now=NOW, tz_name="Europe/Madrid") is None


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.eqs = []
        self._update = None
        self._upsert = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.eqs.append((column, value))
        return self

    def or_(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def update(self, payload):
        self._update = payload
        return self

    def upsert(self, payload, **_k):
        self._upsert = payload
        return self

    def execute(self):
        rows = self.db.tables.setdefault(self.name, [])
        if self._upsert is not None:
            rows.append(dict(self._upsert))
            return _Result([self._upsert])
        matched = [row for row in rows if all(row.get(c) == v for c, v in self.eqs)]
        if self._update is not None:
            for row in matched:
                row.update(self._update)
        return _Result(matched)


class _DB:
    def __init__(self):
        self.tables = {
            "company_feature_flags": [{"company_id": "co-1", "flag": "HOY_MEETINGS_ENABLED", "enabled": True}],
            "memos": [], "meeting_proposals": [], "action_signals": [],
        }

    def table(self, name):
        return _Query(self, name)


def _refresh(db, handoffs):
    from app.services import feature_flags

    feature_flags.clear_cache()
    try:
        return refresh_meeting_today(
            db, company_id="co-1", user_id="ae-1", now=NOW, tz_name="Europe/Madrid", handoffs=handoffs,
        )
    finally:
        feature_flags.clear_cache()


def test_refresh_materializes_the_handoff_meeting_for_the_ae():
    db = _DB()
    assert _refresh(db, [_handoff()]) == 1
    stored = db.tables["action_signals"]
    assert [row["dedupe_key"] for row in stored] == [f"{HANDOFF_KEY_PREFIX}h-1"]
    assert stored[0]["user_id"] == "ae-1"


def test_an_unread_handoff_list_never_resolves_a_stored_handoff_card():
    db = _DB()
    db.tables["action_signals"] = [{
        "id": "sig-h", "company_id": "co-1", "user_id": "ae-1", "type": MEETING_TYPE,
        "dedupe_key": f"{HANDOFF_KEY_PREFIX}h-1", "status": "pending", "version": 1, "payload": {},
    }]
    _refresh(db, None)
    assert db.tables["action_signals"][0]["status"] == "pending"


def test_no_handoffs_left_resolves_a_stored_handoff_card():
    """Self-review fix: flag off (or the AE became an SDR) passes [] - the card resolves
    instead of staying "Reunión hoy" forever. Only None (a failed read) keeps it."""
    db = _DB()
    db.tables["action_signals"] = [{
        "id": "sig-h", "company_id": "co-1", "user_id": "ae-1", "type": MEETING_TYPE,
        "dedupe_key": f"{HANDOFF_KEY_PREFIX}h-1", "status": "pending", "version": 1, "payload": {},
    }]
    _refresh(db, [])
    assert db.tables["action_signals"][0]["status"] == "resolved"
