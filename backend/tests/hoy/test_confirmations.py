"""E7: confirm_pending after auto-approve — signal, confirm action, deferred CRM write."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-confirm-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-confirm-32")
os.environ.setdefault("HOY_CONFIRMATIONS_ENABLED", "false")

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import today as today_api
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.hoy.confirmations import (
    CONFIRM_FLAG,
    CONFIRM_TYPE,
    DealSnapshot,
    apply_confirm_writes,
    build_confirm_signal,
    confirm_write_due,
    flush_due_confirm_writes,
    pending_confirm_parts,
)
from app.services.hoy.done import done_today
from app.services.hoy.actions import apply_action, undo_action

NOW = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
COMPANY = "co-confirm"
USER = "user-rep"
MEMO = "memo-confirm-1"
SIGNAL = "sig-confirm-1"

CONFIG = SimpleNamespace(
    meeting_booked_pipeline_id="default",
    meeting_booked_stage_id="appointmentscheduled",
)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store: "_Store", name: str, payload: dict | None = None):
        self._store = store
        self._name = name
        self._payload = payload
        self._filters: list = []

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def update(self, payload):
        return _Query(self._store, self._name, payload)

    def upsert(self, payload, **_k):
        self._payload = payload
        return self

    def limit(self, _n):
        return self

    def execute(self):
        rows = list(self._store.tables.get(self._name, []))
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        if self._payload is not None and self._name == "action_signals":
            if "dedupe_key" in (self._payload or {}):
                key = self._payload.get("dedupe_key")
                existing = next((r for r in self._store.tables["action_signals"] if r.get("dedupe_key") == key), None)
                if existing:
                    existing.update(self._payload)
                    return _Result([existing])
                row = {"id": SIGNAL, "version": 1, **self._payload}
                self._store.tables["action_signals"].append(row)
                return _Result([row])
            for row in rows:
                row.update(self._payload)
            return _Result(rows)
        return _Result(rows)


class _Store:
    def __init__(self, **tables):
        self.tables = tables

    def table(self, name):
        return _Query(self, name)


@pytest.fixture(autouse=True)
def fresh_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


def _memo(**overrides):
    row = {
        "id": MEMO,
        "company_id": COMPANY,
        "user_id": USER,
        "hubspot_contact_id": "c1",
        "hubspot_deal_id": "d1",
        "connection_id": "conn-1",
        "extraction": {"contactName": "Marina", "dealStage": "qualifiedtobuy"},
    }
    row.update(overrides)
    return row


def _proposal(**overrides):
    row = {
        "memo_id": MEMO,
        "proposal_id": "meet-1",
        "agreement": "agreed",
        "decision": "pending",
        "starts_at": "2026-10-01T09:00:00+00:00",
        "created_at": "2026-09-26T09:00:00Z",
    }
    row.update(overrides)
    return row


def _flags(on: bool):
    return [{"company_id": COMPANY, "flag": CONFIRM_FLAG, "enabled": on}]


def _stage_flags(on: bool):
    return [{"company_id": COMPANY, "flag": "DEAL_STAGE_CONFIRM_ENABLED", "enabled": on}]


def test_different_stage_yields_pending_parts():
    db = _Store(company_feature_flags=[*_flags(True), *_stage_flags(True)])
    deal = DealSnapshot(provider="hubspot", pipeline_id="default", stage_id="qualifiedtobuy")
    pending = pending_confirm_parts(
        memo=_memo(extraction={"contactName": "Marina", "dealStage": "appointmentscheduled"}),
        proposal_rows=[],
        config=CONFIG,
        deal=deal,
        supabase=db,
        company_id=COMPANY,
    )
    assert pending is not None
    assert pending.stage is not None
    assert pending.stage["stage_id"] == "appointmentscheduled"
    assert pending.meeting is None


def test_same_stage_yields_nothing():
    db = _Store(company_feature_flags=[*_flags(True), *_stage_flags(True)])
    deal = DealSnapshot(provider="hubspot", pipeline_id="default", stage_id="qualifiedtobuy")
    assert pending_confirm_parts(
        memo=_memo(),
        proposal_rows=[],
        config=CONFIG,
        deal=deal,
        supabase=db,
        company_id=COMPANY,
    ) is None


def test_unaccepted_meeting_yields_pending():
    db = _Store(company_feature_flags=_flags(True))
    pending = pending_confirm_parts(
        memo=_memo(),
        proposal_rows=[_proposal()],
        config=CONFIG,
        deal=None,
        supabase=db,
        company_id=COMPANY,
    )
    assert pending is not None
    assert pending.meeting is not None
    assert pending.stage is None


def test_accepted_meeting_yields_nothing():
    db = _Store(company_feature_flags=_flags(True))
    assert pending_confirm_parts(
        memo=_memo(),
        proposal_rows=[_proposal(decision="accepted")],
        config=CONFIG,
        deal=None,
        supabase=db,
        company_id=COMPANY,
    ) is None


def test_stage_and_meeting_one_pending():
    db = _Store(company_feature_flags=[*_flags(True), *_stage_flags(True)])
    deal = DealSnapshot(provider="hubspot", pipeline_id="default", stage_id="qualifiedtobuy")
    pending = pending_confirm_parts(
        memo=_memo(),
        proposal_rows=[_proposal()],
        config=CONFIG,
        deal=deal,
        supabase=db,
        company_id=COMPANY,
    )
    assert pending.meeting and pending.stage
    signal = build_confirm_signal(pending, [_proposal()], tz_name="Europe/Madrid")
    assert signal.type == CONFIRM_TYPE
    assert signal.dedupe_key == f"confirm:{MEMO}"
    assert "reunión" in signal.payload["reason"].lower()
    assert signal.payload.get("detail")


def test_flag_off_yields_nothing():
    db = _Store(company_feature_flags=_flags(False))
    deal = DealSnapshot(provider="hubspot", pipeline_id="default", stage_id="qualifiedtobuy")
    assert pending_confirm_parts(
        memo=_memo(),
        proposal_rows=[_proposal()],
        config=CONFIG,
        deal=deal,
        supabase=db,
        company_id=COMPANY,
    ) is None


@pytest.mark.asyncio
async def test_confirm_writes_use_review_functions_once():
    db = _Store()
    row = {
        "memo_id": MEMO,
        "payload": {
            "meeting": {"proposal_id": "meet-1"},
            "stage": {"stage_id": "appointmentscheduled", "stage_label": "Meeting booked", "field": "dealstage"},
        },
    }
    with patch("app.services.hoy.confirmations.accept_meeting_proposal") as accept_mock, patch(
        "app.services.hoy.confirmations.write_confirmed_stage", new_callable=AsyncMock
    ) as stage_mock:
        first = await apply_confirm_writes(db, row=row, company_id=COMPANY, user_id=USER)
        second = await apply_confirm_writes(db, row={**row, "payload": {**row["payload"], "write_applied": True}}, company_id=COMPANY, user_id=USER)
    assert first["replayed"] is False
    assert second["replayed"] is True
    accept_mock.assert_called_once()
    stage_mock.assert_awaited_once()


def test_undo_within_window_clears_write_pending():
    row = {
        "id": SIGNAL,
        "company_id": COMPANY,
        "user_id": USER,
        "type": CONFIRM_TYPE,
        "status": "pending",
        "version": 1,
        "payload": {"meeting": {"proposal_id": "meet-1"}},
    }
    confirmed = apply_action(
        row,
        action="confirm",
        request_id="req-1",
        expected_version=1,
        until=None,
        now=NOW,
        user_id=USER,
        company_id=COMPANY,
    )
    payload = {"write_pending": True, **row["payload"]}
    confirmed_row = {**row, **confirmed, "payload": payload, "undo_deadline": confirmed["undo_deadline"]}
    assert confirm_write_due(confirmed_row, NOW + timedelta(seconds=2)) is False
    undone = undo_action(
        confirmed_row,
        request_id="req-1",
        expected_version=2,
        now=NOW + timedelta(seconds=3),
        user_id=USER,
        company_id=COMPANY,
    )
    assert undone["status"] == "pending"


@pytest.mark.asyncio
async def test_flush_after_undo_window_writes_once():
    db = _Store(
        company_feature_flags=_flags(True),
        action_signals=[{
            "id": SIGNAL,
            "company_id": COMPANY,
            "user_id": USER,
            "type": CONFIRM_TYPE,
            "status": "resolved",
            "memo_id": MEMO,
            "undo_deadline": (NOW - timedelta(seconds=1)).isoformat(),
            "payload": {"write_pending": True, "meeting": {"proposal_id": "meet-1"}},
        }],
    )
    with patch("app.services.hoy.confirmations.apply_confirm_writes", new_callable=AsyncMock) as apply_mock:
        apply_mock.return_value = {"replayed": False}
        count = await flush_due_confirm_writes(db, company_id=COMPANY, user_id=USER, now=NOW)
    assert count == 1
    payload = db.tables["action_signals"][0]["payload"]
    assert payload.get("write_applied") is True
    assert "write_pending" not in payload


def test_confirm_on_non_confirm_signal_rejected():
    row = {
        "id": SIGNAL,
        "company_id": COMPANY,
        "user_id": USER,
        "type": "going_cold",
        "status": "pending",
        "version": 1,
    }
    store = _Store(action_signals=[row], company_feature_flags=_flags(True))
    today_api._CLOCK[0] = NOW
    today_api.set_today_tasks(lambda _c: ([], "unavailable"))
    app = FastAPI()
    app.include_router(today_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=USER, role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: store
    client = TestClient(app)
    response = client.post(
        f"/api/v1/today/{SIGNAL}/resolve",
        json={"action": "confirm", "request_id": "r1", "expected_version": 1},
    )
    assert response.status_code == 422


def test_flag_off_hides_confirm_and_rejects_action():
    row = {
        "id": SIGNAL,
        "company_id": COMPANY,
        "user_id": USER,
        "type": CONFIRM_TYPE,
        "status": "pending",
        "version": 1,
        "dedupe_key": f"confirm:{MEMO}",
        "memo_id": MEMO,
        "payload": {"reason": "Confirma: reunión", "meeting": {"proposal_id": "meet-1"}},
        "coverage": "complete",
        "connection_id": "conn",
    }
    store = _Store(action_signals=[row], company_feature_flags=_flags(False))
    today_api._CLOCK[0] = NOW
    today_api.set_today_tasks(lambda _c: ([], "unavailable"))
    app = FastAPI()
    app.include_router(today_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=USER, role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: store
    client = TestClient(app)
    assert client.get("/api/v1/today").json()["items"] == []
    assert client.post(
        f"/api/v1/today/{SIGNAL}/resolve",
        json={"action": "confirm", "request_id": "r1", "expected_version": 1},
    ).status_code == 404


def test_done_lists_confirmation_kind():
    rows = done_today(
        signals=[{
            "type": CONFIRM_TYPE,
            "status": "resolved",
            "last_action_at": NOW.isoformat(),
            "undo_deadline": (NOW + timedelta(seconds=5)).isoformat(),
            "previous_status": "pending",
            "memo_id": MEMO,
            "contact_id": "c1",
        }],
        followups=[],
        calls=[],
        names=({}, {}),
        now=NOW,
        tz_name="Europe/Madrid",
    )
    assert len(rows) == 1
    assert rows[0]["kind"] == "confirmation"


@pytest.mark.asyncio
async def test_salesforce_deal_snapshot_is_none():
    """Auto-approve hook is HubSpot-only; Salesforce gets no deal snapshot for stage confirm."""
    from app.services.hoy.confirmations import fetch_deal_snapshot

    store = _Store(
        crm_connections=[{
            "id": "c1",
            "company_id": COMPANY,
            "provider": "salesforce",
            "status": "connected",
        }]
    )
    with patch(
        "app.services.crm_providers.resolve.resolve_sync_connection_for_company",
        return_value=store.tables["crm_connections"][0],
    ):
        assert await fetch_deal_snapshot(store, memo=_memo(), company_id=COMPANY) is None


@pytest.mark.asyncio
async def test_materialize_after_auto_approve_inserts_signal():
    store = _Store(
        memos=[_memo()],
        meeting_proposals=[_proposal()],
        company_feature_flags=_flags(True),
        action_signals=[],
    )
    deal = DealSnapshot(provider="hubspot", pipeline_id="default", stage_id="qualifiedtobuy")
    with patch(
        "app.services.hoy.confirmations.fetch_deal_snapshot",
        new_callable=AsyncMock,
        return_value=deal,
    ), patch(
        "app.services.crm_config.CRMConfigurationService.get_configuration",
        new_callable=AsyncMock,
        return_value=CONFIG,
    ):
        from app.services.hoy.confirmations import materialize_confirm_after_auto_approve

        ok = await materialize_confirm_after_auto_approve(
            store, memo_id=MEMO, user_id=USER, company_id=COMPANY,
        )
    assert ok is True
    assert len(store.tables["action_signals"]) == 1
    assert store.tables["action_signals"][0]["type"] == CONFIRM_TYPE
