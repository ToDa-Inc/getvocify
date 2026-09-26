"""E5: accepted F14 meetings with starts_at today appear in Hoy behind HOY_MEETINGS_ENABLED."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-meetings")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-meetings")
os.environ.setdefault("HOY_MEETINGS_ENABLED", "false")

import copy
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import today as today_api
from app.config import settings
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.hoy.reasons import meeting_detail, reason
from app.services.hoy.scheduler import build_today_view
from app.services.hoy.signals import Signal, rank_cards
from app.services.meetings.today import (
    MEETINGS_FLAG,
    MEETING_TYPE,
    meeting_dedupe_key,
    meeting_today_signal,
    refresh_meeting_today,
)

MADRID = "Europe/Madrid"
NOW = datetime(2026, 9, 29, 8, 0, tzinfo=timezone.utc)  # 10:00 Madrid
COMPANY = "co-meet"
USER = "user-rep"
MEMO = "memo-meet-1"
PROPOSAL = "prop-1"
CONNECTION = {"id": "crm-A", "provider": "hubspot", "status": "connected", "company_id": COMPANY}


def _memo(**extra) -> dict:
    base = {
        "id": MEMO,
        "user_id": USER,
        "company_id": COMPANY,
        "hubspot_contact_id": "42",
        "connection_id": "crm-A",
        "approved_at": "2026-09-24T10:00:00Z",
        "extraction": {"summary": "Demo de producto", "intelligence": {}},
    }
    base.update(extra)
    return base


def _proposal(**extra) -> dict:
    base = {
        "proposal_id": PROPOSAL,
        "memo_id": MEMO,
        "input_revision": "rev-1",
        "agreement": "agreed",
        "starts_at": "2026-09-29T09:00:00Z",  # 11:00 Madrid
        "timezone": MADRID,
        "precision": "exact",
        "decision": "accepted",
        "crm_status": "succeeded",
        "created_at": "2026-09-24T10:00:00Z",
    }
    base.update(extra)
    return base


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store: "_Store", name: str):
        self._store = store
        self._name = name
        self._filters: list = []
        self._op: str | None = None
        self._payload: dict | None = None
        self._in_filters: list[tuple[str, list]] = []

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def in_(self, column, values):
        self._in_filters.append((column, list(values)))
        return self

    def limit(self, _n):
        return self

    def order(self, *_a, **_k):
        return self

    def or_(self, _filter):
        return self

    def upsert(self, payload, **_k):
        self._op, self._payload = "upsert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def execute(self):
        table = self._store.tables.setdefault(self._name, [])
        rows = list(table)
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self._in_filters:
            allowed = {str(v) for v in values}
            rows = [row for row in rows if str(row.get(column) or "") in allowed]
        if self._op == "upsert":
            key_cols = ("company_id", "user_id", "connection_id", "dedupe_key")
            match = next(
                (row for row in table if all(row.get(c) == self._payload.get(c) for c in key_cols)),
                None,
            )
            if match:
                match.update(copy.deepcopy(self._payload))
            else:
                row = copy.deepcopy(self._payload)
                row.setdefault("id", f"sig-{len(table) + 1}")
                row.setdefault("version", 1)
                row.setdefault("status", "pending")
                table.append(row)
            return _Result([self._payload])
        if self._op == "update":
            updated = []
            for row in table:
                if all(row.get(c) == v for c, v in self._filters):
                    row.update(copy.deepcopy(self._payload))
                    updated.append(row)
            return _Result(updated)
        return _Result(copy.deepcopy(rows))


class _Store:
    def __init__(self):
        self.tables: dict = {}
        self.writes: list = []

    def table(self, name: str):
        return _Query(self, name)


# --- pure rules -----------------------------------------------------------------------------


def test_accepted_with_time_today_is_a_signal():
    signal = meeting_today_signal(_proposal(), _memo(), now=NOW, tz_name=MADRID)
    assert signal is not None
    assert signal.type == MEETING_TYPE
    assert signal.contact_id == "42"
    assert signal.dedupe_key == meeting_dedupe_key(PROPOSAL)
    assert signal.payload["precision"] == "time"
    assert signal.due_at is not None
    assert signal.due_at.hour == 9


def test_date_only_today_has_no_time_precision():
    signal = meeting_today_signal(
        _proposal(starts_at="2026-09-28T22:00:00Z", precision="date_only"),
        _memo(),
        now=NOW,
        tz_name=MADRID,
    )
    assert signal is not None
    assert signal.payload["precision"] == "date"


def test_yesterday_and_tomorrow_are_out():
    yesterday = meeting_today_signal(
        _proposal(starts_at="2026-09-28T09:00:00Z"),
        _memo(),
        now=NOW,
        tz_name=MADRID,
    )
    tomorrow = meeting_today_signal(
        _proposal(starts_at="2026-09-30T09:00:00Z"),
        _memo(),
        now=NOW,
        tz_name=MADRID,
    )
    assert yesterday is None
    assert tomorrow is None


def test_midnight_edges_use_the_rep_calendar_not_timedelta():
    # Meeting at 23:30 Madrid on the 28th is not "today" on the 29th at 00:30 Madrid.
    late = meeting_today_signal(
        _proposal(starts_at="2026-09-28T21:30:00Z"),
        _memo(),
        now=datetime(2026, 9, 28, 22, 30, tzinfo=timezone.utc),
        tz_name=MADRID,
    )
    early = meeting_today_signal(
        _proposal(starts_at="2026-09-28T22:30:00Z"),
        _memo(),
        now=datetime(2026, 9, 28, 22, 30, tzinfo=timezone.utc),
        tz_name=MADRID,
    )
    assert late is None
    assert early is not None


def test_omitted_and_pending_stay_out():
    assert meeting_today_signal(_proposal(decision="omitted"), _memo(), now=NOW, tz_name=MADRID) is None
    assert meeting_today_signal(_proposal(decision="pending"), _memo(), now=NOW, tz_name=MADRID) is None
    assert meeting_today_signal(_proposal(agreement="unknown"), _memo(), now=NOW, tz_name=MADRID) is None


def test_detail_shows_acceptance_date_in_local_calendar():
    signal = meeting_today_signal(_proposal(), _memo(), now=NOW, tz_name=MADRID)
    assert signal is not None
    assert meeting_detail(signal.payload, lang="es") == "acordada el 24 sep"
    view = build_today_view(
        signals=[signal],
        manual_tasks=[],
        now=NOW,
        coverage={"intelligence": "complete", "crm_tasks": "complete"},
        generated_at=NOW.isoformat(),
        lang="es",
        tz_name=MADRID,
    )
    item = view["items"][0]
    assert item["detail"] == "acordada el 24 sep"


def test_reason_is_short_and_localized():
    signal = meeting_today_signal(_proposal(), _memo(), now=NOW, tz_name=MADRID)
    assert signal is not None
    assert "Demo" in reason(signal, lang="es")
    bare = meeting_today_signal(_proposal(), _memo(extraction={}), now=NOW, tz_name=MADRID)
    assert bare is not None
    assert reason(bare, lang="en") == "Meeting agreed"
    assert reason(bare, lang="es") == "Reunión acordada"


def test_rank_cards_sorts_meetings_by_local_time():
    later = meeting_today_signal(
        _proposal(proposal_id="p-late", starts_at="2026-09-29T14:00:00Z"),
        _memo(),
        now=NOW,
        tz_name=MADRID,
    )
    earlier = meeting_today_signal(
        _proposal(proposal_id="p-early", starts_at="2026-09-29T08:00:00Z"),
        _memo(id="memo-2"),
        now=NOW,
        tz_name=MADRID,
    )
    cards, _folded = rank_cards([later, earlier], now=NOW)
    assert cards[0].primary.dedupe_key == meeting_dedupe_key("p-early")


def test_rematerialize_is_idempotent():
    store = _Store()
    store.tables["memos"] = [_memo()]
    store.tables["meeting_proposals"] = [_proposal()]
    store.tables["action_signals"] = []
    store.tables["company_feature_flags"] = [{"company_id": COMPANY, "flag": MEETINGS_FLAG, "enabled": True}]
    first = refresh_meeting_today(store, company_id=COMPANY, user_id=USER, now=NOW, tz_name=MADRID)
    second = refresh_meeting_today(store, company_id=COMPANY, user_id=USER, now=NOW, tz_name=MADRID)
    assert first == 1
    assert second == 0
    assert len(store.tables["action_signals"]) == 1


# --- GET /today -----------------------------------------------------------------------------


@pytest.fixture
def today_store(monkeypatch):
    store = _Store()
    store.tables["crm_connections"] = [CONNECTION]
    store.tables["memos"] = [_memo()]
    store.tables["meeting_proposals"] = [_proposal()]
    store.tables["action_signals"] = []
    store.tables["company_feature_flags"] = []
    monkeypatch.setattr(today_api, "_TASKS", lambda _cid: ([], "complete"))
    monkeypatch.setattr(today_api, "_CLOCK", [NOW])
    monkeypatch.setattr(feature_flags, "is_enabled", feature_flags.is_enabled)
    return store


def _client(store: _Store) -> TestClient:
    today_api._CLOCK[0] = NOW
    app = FastAPI()
    app.include_router(today_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m",
        company_id=COMPANY,
        user_id=USER,
        role="member",
        status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


def test_flag_off_today_is_unchanged(today_store, monkeypatch):
    feature_flags.clear_cache()
    store = today_store
    monkeypatch.setattr(settings, "HOY_MEETINGS_ENABLED", False)
    body = _client(store).get("/api/v1/today").json()
    assert body["items"] == []
    assert all(item.get("type") != MEETING_TYPE for item in body["items"])


def test_flag_on_shows_meeting_card(today_store, monkeypatch):
    feature_flags.clear_cache()
    store = today_store
    monkeypatch.setattr(settings, "HOY_MEETINGS_ENABLED", False)
    store.tables["company_feature_flags"] = [{"company_id": COMPANY, "flag": MEETINGS_FLAG, "enabled": True}]
    body = _client(store).get("/api/v1/today").json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["type"] == MEETING_TYPE
    assert item["contact_id"] == "42"
    assert item["due_at"] in {"2026-09-29T09:00:00+00:00", "2026-09-29T09:00:00Z"}
    assert item["precision"] == "time"
    assert item["detail"] == "acordada el 24 sep"
    assert item["id"]
