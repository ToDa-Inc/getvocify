"""E7: confirm_pending after auto-approve — signal, confirm action, deferred CRM write."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-confirm-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-confirm-32")
os.environ.setdefault("HOY_CONFIRMATIONS_ENABLED", "false")

import asyncio
import copy
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
from app.services.hoy import confirmations
from app.services.hoy.confirmations import (
    CONFIRM_FLAG,
    CONFIRM_TYPE,
    MAX_WRITE_ATTEMPTS,
    DealSnapshot,
    build_confirm_signal,
    claim_confirm_write,
    confirm_write_due,
    pending_confirm_parts,
    run_confirm_write,
    schedule_confirm_write,
    sweep_confirm_writes,
)
from app.services.hoy.done import done_today
from app.services.hoy.scheduler import confirm_item

NOW = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
COMPANY = "co-confirm"
USER = "user-rep"
MEMO = "memo-confirm-1"
SIGNAL = "sig-confirm-1"

CONFIG = SimpleNamespace(
    meeting_booked_pipeline_id="default",
    meeting_booked_stage_id="appointmentscheduled",
)
BOOKED_LABELS = {"appointmentscheduled": "Meeting booked", "qualifiedtobuy": "Qualified"}


class _Result:
    def __init__(self, data):
        self.data = data


def _matches(row: dict, column: str, value) -> bool:
    if "->>" in column:
        base, key = column.split("->>", 1)
        stored = (row.get(base) or {}).get(key)
        return str(stored).lower() == str(value).lower() if stored is not None else False
    return row.get(column) == value


class _Query:
    def __init__(self, store: "_Store", name: str):
        self._store = store
        self._name = name
        self._filters: list = []
        self._op: str | None = None
        self._payload: dict | None = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, _n):
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def upsert(self, payload, **_k):
        self._op, self._payload = "upsert", payload
        return self

    def execute(self):
        table = self._store.tables.setdefault(self._name, [])
        rows = [row for row in table if all(_matches(row, c, v) for c, v in self._filters)]
        if self._op == "update":
            self._store.writes.append((self._name, copy.deepcopy(self._payload)))
            for row in rows:
                row.update(copy.deepcopy(self._payload))
            return _Result([dict(row) for row in rows])
        if self._op == "upsert":
            self._store.writes.append((self._name, copy.deepcopy(self._payload)))
            key = self._payload.get("dedupe_key")
            existing = next((r for r in table if r.get("dedupe_key") == key), None)
            if existing:
                existing.update(copy.deepcopy(self._payload))
                return _Result([dict(existing)])
            row = {"id": SIGNAL, "version": 1, **copy.deepcopy(self._payload)}
            table.append(row)
            return _Result([dict(row)])
        return _Result([copy.deepcopy(row) for row in rows])


class _Store:
    def __init__(self, **tables):
        self.tables = tables
        self.writes: list = []

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


def _deal(**overrides):
    values = {
        "provider": "hubspot",
        "pipeline_id": "default",
        "stage_id": "qualifiedtobuy",
        "stage_labels": BOOKED_LABELS,
    }
    values.update(overrides)
    return DealSnapshot(**values)


def _both_pending():
    db = _Store(company_feature_flags=[*_flags(True), *_stage_flags(True)])
    return pending_confirm_parts(
        memo=_memo(),
        proposal_rows=[_proposal()],
        config=CONFIG,
        deal=_deal(),
        supabase=db,
        company_id=COMPANY,
    )


def _signal_row(**overrides):
    row = {
        "id": SIGNAL,
        "company_id": COMPANY,
        "user_id": USER,
        "connection_id": "conn-1",
        "type": CONFIRM_TYPE,
        "status": "pending",
        "version": 1,
        "memo_id": MEMO,
        "contact_id": "c1",
        "dedupe_key": f"confirm:{MEMO}",
        "coverage": "complete",
        "payload": {
            "reason": "Confirma: reunión jue 1 oct, 11:00 con Marina · etapa → Meeting booked",
            "contact_name": "Marina",
            "meeting": {"proposal_id": "meet-1", "starts_at": "2026-10-01T09:00:00+00:00"},
            "stage": {
                "field": "dealstage",
                "stage_id": "appointmentscheduled",
                "stage_label": "Meeting booked",
                "current_stage_id": "qualifiedtobuy",
            },
        },
    }
    row.update(overrides)
    return row


def _due_row(**payload_overrides):
    real_now = datetime.now(timezone.utc)
    row = _signal_row(
        status="resolved",
        version=2,
        previous_status="pending",
        last_action_request_id="req-1",
        last_action_at=(real_now - timedelta(seconds=10)).isoformat(),
        undo_deadline=(real_now - timedelta(seconds=5)).isoformat(),
    )
    row["payload"] = {**row["payload"], "write_pending": True, **payload_overrides}
    return row


def _client(store) -> TestClient:
    today_api._CLOCK[0] = NOW
    today_api.set_today_tasks(lambda _c: ([], "unavailable"))
    app = FastAPI()
    app.include_router(today_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id=COMPANY, user_id=USER, role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: store
    return TestClient(app)


# --- Señal ------------------------------------------------------------------


def test_different_stage_yields_pending_parts():
    db = _Store(company_feature_flags=[*_flags(True), *_stage_flags(True)])
    pending = pending_confirm_parts(
        memo=_memo(extraction={"contactName": "Marina", "dealStage": "appointmentscheduled"}),
        proposal_rows=[],
        config=CONFIG,
        deal=_deal(),
        supabase=db,
        company_id=COMPANY,
    )
    assert pending is not None
    assert pending.stage["stage_id"] == "appointmentscheduled"
    assert pending.stage["stage_label"] == "Meeting booked"
    assert pending.meeting is None


def test_same_stage_yields_nothing():
    db = _Store(company_feature_flags=[*_flags(True), *_stage_flags(True)])
    assert pending_confirm_parts(
        memo=_memo(),
        proposal_rows=[],
        config=CONFIG,
        deal=_deal(),
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
    assert pending.meeting == {"proposal_id": "meet-1", "starts_at": "2026-10-01T09:00:00+00:00"}
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


def test_omitted_meeting_yields_nothing():
    db = _Store(company_feature_flags=[*_flags(True), *_stage_flags(True)])
    assert pending_confirm_parts(
        memo=_memo(),
        proposal_rows=[_proposal(decision="omitted")],
        config=CONFIG,
        deal=_deal(),
        supabase=db,
        company_id=COMPANY,
    ) is None


def test_pending_parts_do_no_io_beyond_flags():
    db = _Store(company_feature_flags=[*_flags(True), *_stage_flags(True)])
    pending_confirm_parts(
        memo=_memo(),
        proposal_rows=[],
        config=CONFIG,
        deal=_deal(),
        supabase=db,
        company_id=COMPANY,
    )
    assert set(db.tables) == {"company_feature_flags"}


def test_stage_and_meeting_one_signal_with_brief_reason():
    pending = _both_pending()
    signal = build_confirm_signal(pending, tz_name="Europe/Madrid")
    assert signal.type == CONFIRM_TYPE
    assert signal.dedupe_key == f"confirm:{MEMO}"
    assert signal.payload["reason"] == "Confirma: reunión jue 1 oct, 11:00 con Marina · etapa → Meeting booked"
    assert "detail" not in signal.payload


def test_reason_meeting_only_and_stage_only():
    pending = _both_pending()
    meeting_only = build_confirm_signal(
        confirmations.PendingConfirm(**{**pending.__dict__, "stage": None}), tz_name="Europe/Madrid",
    )
    stage_only = build_confirm_signal(
        confirmations.PendingConfirm(**{**pending.__dict__, "meeting": None}), tz_name="Europe/Madrid",
    )
    assert meeting_only.payload["reason"] == "Confirma: reunión jue 1 oct, 11:00 con Marina"
    assert stage_only.payload["reason"] == "Confirma: etapa → Meeting booked"


def test_stage_label_comes_from_the_crm_stage_name():
    db = _Store(company_feature_flags=[*_flags(True), *_stage_flags(True)])
    pending = pending_confirm_parts(
        memo=_memo(),
        proposal_rows=[_proposal()],
        config=CONFIG,
        deal=_deal(stage_labels={"appointmentscheduled": "Cita agendada"}),
        supabase=db,
        company_id=COMPANY,
    )
    assert pending.stage["stage_label"] == "Cita agendada"
    reason = build_confirm_signal(pending, tz_name="Europe/Madrid").payload["reason"]
    assert reason.endswith("· etapa → Cita agendada")


def test_today_item_reason_follows_the_rep_language():
    row = _signal_row()
    en = confirm_item(row, lang="en", tz_name="Europe/Madrid")
    es = confirm_item(row, lang="es", tz_name="Europe/Madrid")
    assert en["reason"] == "Confirm: meeting Thu 1 Oct, 11:00 with Marina · stage → Meeting booked"
    assert es["reason"] == "Confirma: reunión jue 1 oct, 11:00 con Marina · etapa → Meeting booked"
    assert es["detail"] is None


def test_flag_off_yields_nothing():
    db = _Store(company_feature_flags=_flags(False))
    assert pending_confirm_parts(
        memo=_memo(),
        proposal_rows=[_proposal()],
        config=CONFIG,
        deal=_deal(),
        supabase=db,
        company_id=COMPANY,
    ) is None


# --- Materialización y enganche ---------------------------------------------


def _materialize_patches(deal):
    return (
        patch("app.services.hoy.confirmations.fetch_deal_snapshot", new_callable=AsyncMock, return_value=deal),
        patch(
            "app.services.crm_config.CRMConfigurationService.get_configuration",
            new_callable=AsyncMock,
            return_value=CONFIG,
        ),
    )


@pytest.mark.asyncio
async def test_materialize_after_auto_approve_inserts_signal():
    store = _Store(
        memos=[_memo()],
        meeting_proposals=[_proposal()],
        company_feature_flags=[*_flags(True), *_stage_flags(True)],
        action_signals=[],
    )
    first, second = _materialize_patches(_deal())
    with first, second:
        ok = await confirmations.materialize_confirm_after_auto_approve(
            store, memo_id=MEMO, user_id=USER, company_id=COMPANY,
        )
    assert ok is True
    [row] = store.tables["action_signals"]
    assert row["type"] == CONFIRM_TYPE
    assert row["status"] == "pending"
    assert row["payload"]["reason"] == "Confirma: reunión jue 1 oct, 11:00 con Marina · etapa → Meeting booked"


@pytest.mark.asyncio
async def test_re_auto_approve_never_reopens_a_resolved_signal():
    applied = _signal_row(status="resolved", version=4)
    applied["payload"] = {**applied["payload"], "write_applied": True}
    store = _Store(
        memos=[_memo()],
        meeting_proposals=[_proposal()],
        company_feature_flags=[*_flags(True), *_stage_flags(True)],
        action_signals=[copy.deepcopy(applied)],
    )
    first, second = _materialize_patches(_deal())
    with first, second:
        ok = await confirmations.materialize_confirm_after_auto_approve(
            store, memo_id=MEMO, user_id=USER, company_id=COMPANY,
        )
    assert ok is False
    assert store.tables["action_signals"] == [applied]


@pytest.mark.asyncio
async def test_non_hubspot_connections_get_no_deal_snapshot():
    for provider in ("salesforce", "pipedrive"):
        connection = {"id": "c1", "company_id": COMPANY, "provider": provider, "status": "connected",
                      "access_token": "t", "metadata": {"api_domain": "https://x.pipedrive.com"}}
        with patch(
            "app.services.crm_providers.resolve.resolve_sync_connection_for_company",
            return_value=connection,
        ):
            assert await confirmations.fetch_deal_snapshot(_Store(), memo=_memo(), company_id=COMPANY) is None


def _auto_sync_env(*, toggle: bool):
    memo = {
        "id": MEMO, "status": "pending_review", "source": "hubspot_call", "company_id": COMPANY,
        "hubspot_contact_id": "c1", "hubspot_deal_id": "d1", "matched_deal_id": None,
        "screening_outcome": None,
    }
    store = _Store(memos=[memo])
    config = SimpleNamespace(auto_sync_hubspot_calls=toggle)
    return store, config


@pytest.mark.asyncio
async def test_without_auto_approve_nothing_is_materialized():
    from app.services.hubspot import auto_sync

    store, config = _auto_sync_env(toggle=False)
    with patch(
        "app.services.crm_config.CRMConfigurationService.get_configuration",
        new_callable=AsyncMock, return_value=config,
    ), patch("app.services.memo_approval.approve_memo_core", new_callable=AsyncMock) as approve, patch(
        "app.services.hoy.confirmations.materialize_confirm_after_auto_approve", new_callable=AsyncMock,
    ) as materialize:
        assert await auto_sync.maybe_auto_approve_hubspot_call(store, MEMO, USER) is False
    approve.assert_not_awaited()
    materialize.assert_not_awaited()


@pytest.mark.asyncio
async def test_materialize_failure_never_breaks_auto_approve():
    from app.services.hubspot import auto_sync

    store, config = _auto_sync_env(toggle=True)
    with patch(
        "app.services.crm_config.CRMConfigurationService.get_configuration",
        new_callable=AsyncMock, return_value=config,
    ), patch("app.services.memo_approval.approve_memo_core", new_callable=AsyncMock) as approve, patch(
        "app.services.hoy.confirmations.materialize_confirm_after_auto_approve",
        new_callable=AsyncMock, side_effect=RuntimeError("boom"),
    ) as materialize:
        assert await auto_sync.maybe_auto_approve_hubspot_call(store, MEMO, USER) is True
    approve.assert_awaited_once()
    materialize.assert_awaited_once()


# --- Acción confirm (HTTP) --------------------------------------------------


def test_resolve_confirm_marks_write_pending_and_schedules_the_write():
    store = _Store(action_signals=[_signal_row()], company_feature_flags=_flags(True))
    with patch.object(today_api, "schedule_confirm_write") as schedule, patch(
        "app.services.hoy.confirmations.apply_confirm_writes", new_callable=AsyncMock,
    ) as apply:
        response = _client(store).post(
            f"/api/v1/today/{SIGNAL}/resolve",
            json={"action": "confirm", "request_id": "r1", "expected_version": 1},
        )
    assert response.status_code == 200
    row = store.tables["action_signals"][0]
    assert row["status"] == "resolved"
    assert row["payload"]["write_pending"] is True
    apply.assert_not_awaited()
    schedule.assert_called_once()
    assert schedule.call_args.args[1] == SIGNAL
    assert schedule.call_args.args[2] == row["undo_deadline"]


def test_resolve_confirm_replay_schedules_once():
    store = _Store(action_signals=[_signal_row()], company_feature_flags=_flags(True))
    with patch.object(today_api, "schedule_confirm_write") as schedule:
        client = _client(store)
        body = {"action": "confirm", "request_id": "r1", "expected_version": 1}
        assert client.post(f"/api/v1/today/{SIGNAL}/resolve", json=body).status_code == 200
        assert client.post(f"/api/v1/today/{SIGNAL}/resolve", json=body).status_code == 200
    schedule.assert_called_once()


def test_undo_within_window_clears_the_pending_write():
    store = _Store(action_signals=[_signal_row()], company_feature_flags=_flags(True))
    with patch.object(today_api, "schedule_confirm_write"):
        client = _client(store)
        client.post(
            f"/api/v1/today/{SIGNAL}/resolve",
            json={"action": "confirm", "request_id": "r1", "expected_version": 1},
        )
        today_api._CLOCK[0] = NOW + timedelta(seconds=3)
        response = client.patch(f"/api/v1/today/{SIGNAL}", json={"request_id": "r1", "expected_version": 2})
    assert response.status_code == 200
    row = store.tables["action_signals"][0]
    assert row["status"] == "pending"
    assert "write_pending" not in row["payload"]
    assert confirm_write_due(row, NOW + timedelta(minutes=5)) is False


@pytest.mark.asyncio
async def test_undone_confirmation_is_never_written_by_the_sweep():
    row = _due_row()
    row.update(status="pending", undo_deadline=None)
    row["payload"].pop("write_pending")
    store = _Store(action_signals=[row], company_feature_flags=_flags(True))
    with patch("app.services.hoy.confirmations.apply_confirm_writes", new_callable=AsyncMock) as apply:
        await sweep_confirm_writes(store, now=datetime.now(timezone.utc))
    apply.assert_not_awaited()


def test_confirm_on_non_confirm_signal_rejected():
    row = _signal_row(type="going_cold", payload={})
    store = _Store(action_signals=[row], company_feature_flags=_flags(True))
    response = _client(store).post(
        f"/api/v1/today/{SIGNAL}/resolve",
        json={"action": "confirm", "request_id": "r1", "expected_version": 1},
    )
    assert response.status_code == 422


def test_flag_off_hides_confirm_and_rejects_action():
    store = _Store(action_signals=[_signal_row()], company_feature_flags=_flags(False))
    client = _client(store)
    assert client.get("/api/v1/today").json()["items"] == []
    response = client.post(
        f"/api/v1/today/{SIGNAL}/resolve",
        json={"action": "confirm", "request_id": "r1", "expected_version": 1},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Señal no encontrada"


def test_flag_on_without_confirm_rows_is_today_as_before():
    other = {
        "id": "sig-cold", "company_id": COMPANY, "user_id": USER, "connection_id": "conn-1",
        "type": "going_cold", "status": "pending", "version": 1, "contact_id": "c9",
        "dedupe_key": "cold:c9", "coverage": "complete",
        "payload": {"days_silent": 14, "interest": "high"},
    }
    off = _client(_Store(action_signals=[dict(other)], company_feature_flags=_flags(False))).get("/api/v1/today").json()
    feature_flags.clear_cache()
    on = _client(_Store(action_signals=[dict(other)], company_feature_flags=_flags(True))).get("/api/v1/today").json()
    assert [item["type"] for item in on["items"]] == ["going_cold"]
    assert on == off


def test_get_today_never_writes_to_the_crm():
    store = _Store(action_signals=[_due_row()], company_feature_flags=_flags(True))
    with patch(
        "app.services.hoy.confirmations.apply_confirm_writes",
        new_callable=AsyncMock, side_effect=RuntimeError("crm down"),
    ) as apply:
        client = _client(store)
        today_api._CLOCK[0] = datetime.now(timezone.utc) + timedelta(minutes=1)
        response = client.get("/api/v1/today")
    assert response.status_code == 200
    apply.assert_not_awaited()


# --- Escritura aplazada -----------------------------------------------------


@pytest.mark.asyncio
async def test_run_writes_through_review_functions_once():
    store = _Store(action_signals=[_due_row()], company_feature_flags=_flags(True))
    with patch("app.services.hoy.confirmations.accept_meeting_proposal") as accept, patch(
        "app.services.hoy.confirmations.write_confirmed_stage", new_callable=AsyncMock,
    ) as stage:
        assert await run_confirm_write(store, SIGNAL) == "applied"
        assert await run_confirm_write(store, SIGNAL) == "skipped"
    accept.assert_called_once()
    assert accept.call_args.kwargs == {
        "company_id": COMPANY, "memo_id": MEMO, "decision": "accept", "proposal_id": "meet-1",
    }
    stage.assert_awaited_once()
    assert stage.call_args.kwargs["stage_id"] == "appointmentscheduled"
    payload = store.tables["action_signals"][0]["payload"]
    assert payload["write_applied"] is True
    assert "write_pending" not in payload and "write_claimed_at" not in payload


@pytest.mark.asyncio
async def test_two_concurrent_runs_write_once():
    store = _Store(action_signals=[_due_row()], company_feature_flags=_flags(True))
    calls = []

    async def slow_apply(*_a, **_k):
        calls.append(1)
        await asyncio.sleep(0.01)

    with patch("app.services.hoy.confirmations.apply_confirm_writes", side_effect=slow_apply):
        results = await asyncio.gather(run_confirm_write(store, SIGNAL), run_confirm_write(store, SIGNAL))
    assert len(calls) == 1
    assert sorted(results) == ["applied", "skipped"]


def test_claim_is_conditional_on_the_version():
    row = _due_row()
    store = _Store(action_signals=[copy.deepcopy(row)])
    now = datetime.now(timezone.utc)
    assert claim_confirm_write(store, row, now) is not None
    assert claim_confirm_write(store, row, now) is None


@pytest.mark.asyncio
async def test_failure_is_logged_retried_and_capped_then_reopens():
    store = _Store(action_signals=[_due_row()], company_feature_flags=_flags(True))
    apply = AsyncMock(side_effect=RuntimeError("hubspot 500"))
    with patch("app.services.hoy.confirmations.apply_confirm_writes", apply), patch.object(
        confirmations.logger, "exception",
    ) as log:
        first = await run_confirm_write(store, SIGNAL)
        row = store.tables["action_signals"][0]
        assert first == "retry"
        assert row["status"] == "resolved"
        assert row["payload"]["write_pending"] is True
        assert row["payload"]["write_attempts"] == 1
        assert "write_claimed_at" not in row["payload"]
        for _ in range(MAX_WRITE_ATTEMPTS - 1):
            last = await run_confirm_write(store, SIGNAL)
        assert last == "failed"
        assert await run_confirm_write(store, SIGNAL) == "skipped"
    assert apply.await_count == MAX_WRITE_ATTEMPTS
    assert log.call_count == MAX_WRITE_ATTEMPTS
    extra = log.call_args.kwargs["extra"]
    assert extra["domain"] == "hoy" and extra["phase"] == "confirm_write_failed" and extra["signal_id"] == SIGNAL
    row = store.tables["action_signals"][0]
    assert row["status"] == "pending"
    assert row["undo_deadline"] is None
    assert row["payload"]["write_failed"] is True
    assert "write_pending" not in row["payload"]
    assert row["payload"]["detail"] == "No se pudo guardar en el CRM. Vuelve a confirmar o revísala."
    item = confirm_item(row, lang="es", tz_name="Europe/Madrid")
    assert item["detail"] == "No se pudo guardar en el CRM. Vuelve a confirmar o revísala."
    assert confirm_item(row, lang="en", tz_name="Europe/Madrid")["detail"] == (
        "Could not save to the CRM. Confirm again or review it."
    )


@pytest.mark.asyncio
async def test_run_never_raises_when_the_store_fails():
    broken = MagicMock()
    broken.table.side_effect = RuntimeError("db down")
    assert await run_confirm_write(broken, SIGNAL) == "error"


def test_confirm_again_after_failure_resets_the_attempts():
    failed = _signal_row(status="pending", version=5)
    failed["payload"] = {**failed["payload"], "write_failed": True, "write_attempts": 3,
                         "write_error": "x", "detail": "No se pudo guardar en el CRM. Vuelve a confirmar o revísala."}
    store = _Store(action_signals=[failed], company_feature_flags=_flags(True))
    with patch.object(today_api, "schedule_confirm_write"):
        response = _client(store).post(
            f"/api/v1/today/{SIGNAL}/resolve",
            json={"action": "confirm", "request_id": "r2", "expected_version": 5},
        )
    assert response.status_code == 200
    payload = store.tables["action_signals"][0]["payload"]
    assert payload["write_pending"] is True
    for key in ("write_failed", "write_attempts", "write_error", "detail"):
        assert key not in payload


@pytest.mark.asyncio
async def test_scheduled_task_writes_after_the_deadline():
    row = _due_row()
    store = _Store(action_signals=[row], company_feature_flags=_flags(True))
    with patch("app.services.hoy.confirmations.apply_confirm_writes", new_callable=AsyncMock) as apply:
        task = schedule_confirm_write(store, SIGNAL, row["undo_deadline"])
        await task
    apply.assert_awaited_once()
    assert store.tables["action_signals"][0]["payload"]["write_applied"] is True


@pytest.mark.asyncio
async def test_scheduled_task_waits_for_the_deadline():
    row = _due_row()
    row["undo_deadline"] = (datetime.now(timezone.utc) + timedelta(seconds=0.3)).isoformat()
    store = _Store(action_signals=[row], company_feature_flags=_flags(True))
    with patch("app.services.hoy.confirmations.apply_confirm_writes", new_callable=AsyncMock) as apply:
        task = schedule_confirm_write(store, SIGNAL, row["undo_deadline"])
        await asyncio.sleep(0.05)
        apply.assert_not_awaited()
        await task
    apply.assert_awaited_once()


@pytest.mark.asyncio
async def test_sweep_writes_due_rows_and_skips_the_rest():
    due = _due_row()
    future = _due_row()
    future.update(id="sig-future", dedupe_key="confirm:m2",
                  undo_deadline=(datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat())
    applied = _due_row(write_applied=True)
    applied.update(id="sig-applied", dedupe_key="confirm:m3")
    applied["payload"].pop("write_pending")
    store = _Store(action_signals=[due, future, applied], company_feature_flags=_flags(True))
    with patch("app.services.hoy.confirmations.apply_confirm_writes", new_callable=AsyncMock) as apply:
        written = await sweep_confirm_writes(store, now=datetime.now(timezone.utc))
    assert written == 1
    apply.assert_awaited_once()
    assert apply.call_args.kwargs["row"]["id"] == SIGNAL


@pytest.mark.asyncio
async def test_stale_claim_is_picked_up_by_the_sweep():
    stale = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    store = _Store(action_signals=[_due_row(write_claimed_at=stale, write_attempts=1)],
                   company_feature_flags=_flags(True))
    fresh = datetime.now(timezone.utc).isoformat()
    busy = _Store(action_signals=[_due_row(write_claimed_at=fresh, write_attempts=1)],
                  company_feature_flags=_flags(True))
    with patch("app.services.hoy.confirmations.apply_confirm_writes", new_callable=AsyncMock) as apply:
        assert await sweep_confirm_writes(store, now=datetime.now(timezone.utc)) == 1
        assert await sweep_confirm_writes(busy, now=datetime.now(timezone.utc)) == 0
    apply.assert_awaited_once()


# --- Hecho hoy --------------------------------------------------------------


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
