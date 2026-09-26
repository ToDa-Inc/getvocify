"""A commitment written as a CRM task shows once in Hoy: the commitment card, carrying the task id."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-task-link")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-task-link")

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import today as today_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.hoy.scheduler import build_today_view
from app.services.hoy.signals import Signal, commitment_task_links, signals_for_contact, touch_from_intelligence
from tests.hoy.test_schedule import _Supabase

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
KEY = "commitment:memo-1:call:2026-09-22"
COVERAGE = {"intelligence": "complete", "crm_tasks": "complete"}


def _due(status: str = "pending") -> Signal:
    return Signal(
        type="commitment_due",
        contact_id="42",
        deal_id=None,
        source_memo_id="memo-1",
        due_at=datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc),
        payload={
            "kind": "call", "origin": "rep_promise", "text": "llamar a las 18:00",
            "signal_id": "sig-1", "version": 1, "status": status,
        },
        dedupe_key=KEY,
        connection_id="crm-A",
    )


def _task(remote_id: str, title: str = "Llamar a las 18:00") -> dict:
    return {"remote_id": remote_id, "title": title, "contact_id": "42", "connection_id": "crm-A"}


def _view(signals, tasks, task_links=None):
    kwargs = {} if task_links is None else {"task_links": task_links}
    return build_today_view(
        signals=signals, manual_tasks=tasks, now=NOW, coverage=COVERAGE,
        generated_at=NOW.isoformat(), **kwargs,
    )


def test_a_pending_commitment_absorbs_its_crm_task():
    view = _view([_due()], [_task("T-1"), _task("T-2")], task_links={KEY: ["T-1"]})
    types = [(item["type"], item["remote_id"]) for item in view["items"]]
    assert types == [("commitment_due", None), ("manual_task", "T-2")]
    card = view["items"][0]
    assert card["crm_task_id"] == "T-1"
    assert card["origins"] == ["detected"]


def test_a_done_or_dismissed_commitment_hides_its_crm_task_too():
    view = _view([], [_task("T-1")], task_links={KEY: ["T-1"]})
    assert view["items"] == []


def test_without_a_signal_yet_the_crm_task_shows_as_before():
    view = _view([], [_task("T-1")], task_links={})
    assert [(item["type"], item["remote_id"]) for item in view["items"]] == [("manual_task", "T-1")]


def test_the_same_title_with_another_id_is_not_the_commitment():
    view = _view([_due()], [_task("T-9", title="llamar a las 18:00")], task_links={KEY: ["T-1"]})
    assert [(item["type"], item["remote_id"]) for item in view["items"]] == [
        ("commitment_due", None), ("manual_task", "T-9"),
    ]


def test_two_commitments_under_one_key_show_one_card():
    view = _view([_due()], [_task("T-1"), _task("T-3")], task_links={KEY: ["T-1", "T-3"]})
    assert [item["type"] for item in view["items"]] == ["commitment_due"]
    assert view["items"][0]["crm_task_id"] == "T-1"


def test_without_task_ids_the_view_is_identical():
    before = _view([_due()], [_task("T-1")])
    assert _view([_due()], [_task("T-1")], task_links={}) == before
    assert all("crm_task_id" not in item for item in before["items"])


def _memo(crm_task_id: str | None = "T-1") -> dict:
    commitment = {
        "id": "com-1", "kind": "call", "origin": "rep_promise", "text": "llamar a las 18:00",
        "due_at": "2026-09-22T18:00:00+02:00", "temporal_precision": "time", "evidence_refs": ["ev-1"],
    }
    if crm_task_id:
        commitment["crm_task_id"] = crm_task_id
    undated = {
        "id": "com-2", "kind": "send", "origin": "rep_promise", "text": "enviar la propuesta",
        "due_at": None, "temporal_precision": "unknown", "evidence_refs": ["ev-2"], "crm_task_id": "T-5",
    }
    return {
        "id": "memo-1",
        "user_id": "user-a",
        "hubspot_contact_id": "42",
        "extraction": {"contactName": "Marina López", "intelligence": {"commitments": [commitment, undated]}},
    }


def test_the_link_key_is_the_signal_key():
    memo = _memo()
    touch = touch_from_intelligence(
        memo_id="memo-1", contact_id="42", deal_id=None,
        at=datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc),
        intelligence=memo["extraction"]["intelligence"],
    )
    [signal] = signals_for_contact([touch], now=NOW, day_end=datetime(2026, 9, 22, 22, 0, tzinfo=timezone.utc))
    assert commitment_task_links([memo]) == {signal.dedupe_key: ["T-1"]}
    assert commitment_task_links([_memo(crm_task_id=None)]) == {}


def _signal_row(status: str) -> dict:
    return {
        "id": "sig-1", "company_id": "co-1", "user_id": "user-a", "status": status, "version": 1,
        "type": "commitment_due", "contact_id": "42", "memo_id": "memo-1", "connection_id": "crm-A",
        "dedupe_key": KEY, "coverage": "complete",
        "payload": {"kind": "call", "origin": "rep_promise", "text": "llamar a las 18:00",
                    "due_at": "2026-09-22T18:00:00+02:00"},
    }


def _get_today(store) -> dict:
    app = FastAPI()
    app.include_router(today_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: store
    today_api.set_today_tasks(lambda _company: ([_task("T-1"), _task("T-2", title="Otra cosa")], "complete"))
    today_api._CLOCK[0] = NOW
    try:
        return TestClient(app).get("/api/v1/today").json()
    finally:
        today_api.set_today_tasks(None)
        today_api._CLOCK[0] = today_api._CLOCK_DEFAULT


def test_get_today_shows_the_commitment_once_with_its_task_id():
    store = _Supabase()
    store.rows = [_signal_row("pending")]
    store.tables["memos"] = [_memo()]
    body = _get_today(store)
    assert [(item["type"], item["remote_id"]) for item in body["items"]] == [
        ("commitment_due", None), ("manual_task", "T-2"),
    ]
    assert body["items"][0]["crm_task_id"] == "T-1"
    assert body["items"][0]["contact_name"] == "Marina López"


def test_get_today_hides_the_task_of_a_commitment_already_done():
    store = _Supabase()
    store.rows = [_signal_row("done")]
    store.tables["memos"] = [_memo()]
    body = _get_today(store)
    assert [(item["type"], item["remote_id"]) for item in body["items"]] == [("manual_task", "T-2")]


def test_get_today_before_the_commitment_is_due_shows_the_task():
    store = _Supabase()
    store.tables["memos"] = [_memo()]
    body = _get_today(store)
    assert [(item["type"], item["remote_id"]) for item in body["items"]] == [
        ("manual_task", "T-1"), ("manual_task", "T-2"),
    ]


def test_get_today_without_task_ids_is_as_before():
    store = _Supabase()
    store.rows = [_signal_row("pending")]
    store.tables["memos"] = [_memo(crm_task_id=None)]
    body = _get_today(store)
    assert [(item["type"], item["remote_id"]) for item in body["items"]] == [
        ("commitment_due", None), ("manual_task", "T-1"), ("manual_task", "T-2"),
    ]
    assert "crm_task_id" not in body["items"][0]
