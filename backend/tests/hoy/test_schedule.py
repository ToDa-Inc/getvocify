"""F05 schedule: one local day, one run. A shared title is not the same task."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-schedule")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-schedule")

import shutil
import socket
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import today as today_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.hoy.scheduler import (
    attach_manual,
    build_today_view,
    claim_daily_run_statement,
    claim_if_due,
    collect_open_tasks,
    company_local_date,
    daily_run_due,
    due_company_ids,
    open_manual_tasks,
    rebind_contact,
    task_request,
)
from app.services.coaching import brief_preferences as brief_preferences_mod
from app.services.coaching.brief_preferences import write_preference
from app.services.hoy.reasons import reason
from app.services.hoy.signals import Signal

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "043_action_signals.sql"
COMPANY = "11111111-1111-1111-1111-111111111111"
NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


def _cold(contact_id: str = "42") -> Signal:
    return Signal(
        type="going_cold",
        contact_id=contact_id,
        deal_id=None,
        source_memo_id="memo-1",
        due_at=None,
        payload={"interest": "high", "days_silent": 12},
        dedupe_key=f"cold:{contact_id}",
        connection_id="crm-A",
    )


def test_the_daily_run_starts_at_the_configured_local_hour():
    before = datetime(2026, 9, 22, 5, 59, tzinfo=timezone.utc)
    at_eight = datetime(2026, 9, 22, 6, 0, tzinfo=timezone.utc)
    assert daily_run_due(before, "Europe/Madrid") is False
    assert daily_run_due(at_eight, "Europe/Madrid") is True
    assert daily_run_due(at_eight, "Europe/Madrid", hour=9) is False
    companies = [
        {"company_id": COMPANY, "timezone": "Europe/Madrid"},
        {"company_id": "22222222-2222-2222-2222-222222222222", "timezone": "Europe/Madrid", "hoy_hour": 9},
    ]
    assert due_company_ids(at_eight, companies) == [COMPANY]


def test_claim_if_due_waits_until_eight_madrid_and_repeats_the_same_statement():
    before_eight_madrid = datetime(2026, 9, 22, 5, 59, tzinfo=timezone.utc)
    at_eight_madrid = datetime(2026, 9, 22, 6, 0, tzinfo=timezone.utc)
    assert claim_if_due(before_eight_madrid, "Europe/Madrid", COMPANY) is None
    first = claim_if_due(at_eight_madrid, "Europe/Madrid", COMPANY)
    local_date = company_local_date(at_eight_madrid, "Europe/Madrid")
    assert first is not None
    assert COMPANY in first
    assert local_date.isoformat() in first
    assert "ON CONFLICT DO NOTHING" in first
    second = claim_if_due(at_eight_madrid, "Europe/Madrid", COMPANY)
    assert second == first
    assert second == claim_daily_run_statement(COMPANY, local_date)
    assert claim_if_due(at_eight_madrid, None, COMPANY) == first


def test_claim_if_due_waits_until_eight_in_america_new_york_winter():
    before_eight_ny = datetime(2026, 1, 15, 11, 0, tzinfo=timezone.utc)
    at_eight_ny = datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc)
    assert claim_if_due(before_eight_ny, "America/New_York", COMPANY) is None
    assert claim_if_due(at_eight_ny, "America/New_York", COMPANY) is not None


def _today_client(user_id: str = "user-a"):
    app = FastAPI()
    app.include_router(today_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id=user_id, role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: STORE
    return TestClient(app)


def test_get_today_claim_uses_brief_preference_timezone(monkeypatch):
    write_preference("user-a", {"highlight_mode": "immediate", "timezone": "America/New_York"})
    captured: dict = {}

    def spy_claim(_supabase, _company_id, _now, tz_name, *, hour=8):
        captured["tz_name"] = tz_name

    monkeypatch.setattr(today_api, "attempt_daily_run_claim", spy_claim)
    today_api.set_today_tasks(lambda _company: ([], "complete"))
    try:
        body = _today_client().get("/api/v1/today").json()
    finally:
        today_api.set_today_tasks(None)
        brief_preferences_mod._STORE.pop("user-a", None)
    assert captured["tz_name"] == "America/New_York"
    assert body["coverage"]["crm_tasks"] == "complete"


def test_get_today_claim_defaults_to_madrid_without_preference(monkeypatch):
    brief_preferences_mod._STORE.pop("user-no-pref", None)
    captured: dict = {}

    def spy_claim(_supabase, _company_id, _now, tz_name, *, hour=8):
        captured["tz_name"] = tz_name

    monkeypatch.setattr(today_api, "attempt_daily_run_claim", spy_claim)
    today_api.set_today_tasks(lambda _company: ([], "complete"))
    try:
        _today_client("user-no-pref").get("/api/v1/today").json()
    finally:
        today_api.set_today_tasks(None)
    assert captured["tz_name"] == "Europe/Madrid"


def test_get_today_claim_defaults_to_madrid_when_preference_read_fails(monkeypatch):
    captured: dict = {}

    def spy_claim(_supabase, _company_id, _now, tz_name, *, hour=8):
        captured["tz_name"] = tz_name

    def broken_read(_user_id):
        raise RuntimeError("preference store unavailable")

    monkeypatch.setattr(today_api, "attempt_daily_run_claim", spy_claim)
    monkeypatch.setattr(today_api, "read_preference", broken_read)
    today_api.set_today_tasks(lambda _company: ([], "complete"))
    try:
        body = _today_client().get("/api/v1/today").json()
    finally:
        today_api.set_today_tasks(None)
    assert captured["tz_name"] == "Europe/Madrid"
    assert body["coverage"]["crm_tasks"] == "complete"


def test_an_open_crm_task_is_read_and_a_finished_one_is_not():
    tasks, coverage = open_manual_tasks(
        "hubspot",
        {"results": [
            {"id": "1", "properties": {"hs_task_subject": "Llamar a Marina", "hs_task_status": "NOT_STARTED", "contact_id": "42"}},
            {"id": "2", "properties": {"hs_task_subject": "Hecho", "hs_task_status": "COMPLETED"}},
        ]},
        connection_id="crm-A",
    )
    assert coverage == "complete"
    assert [task["remote_id"] for task in tasks] == ["1"]
    partial, partial_coverage = open_manual_tasks(
        "pipedrive",
        {"data": [{"id": 9, "subject": "Seguir", "done": False, "person_id": 42}], "additional_data": {"next_cursor": "n"}},
        connection_id="crm-A",
    )
    assert partial_coverage == "partial"
    assert partial[0]["title"] == "Seguir"
    forbidden, forbidden_coverage = open_manual_tasks("hubspot", {"error_kind": "403"}, connection_id="crm-A")
    assert forbidden == []
    assert forbidden_coverage == "forbidden"


def test_today_shows_tasks_when_a_reader_is_installed():
    STORE.rows = []
    today_api.set_today_tasks(lambda _company: (
        [{"remote_id": "task-9", "title": "Llamar a Marina", "contact_id": "42", "connection_id": "crm-A"}],
        "complete",
    ))
    try:
        app = FastAPI()
        app.include_router(today_api.router)
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id="co-1", user_id="user-a", role="member", status="active",
        )
        app.dependency_overrides[get_supabase] = lambda: STORE
        body = TestClient(app).get("/api/v1/today").json()
    finally:
        today_api.set_today_tasks(None)
    assert body["coverage"]["crm_tasks"] == "complete"
    assert body["items"][0]["remote_id"] == "task-9"
    assert body["pulse"] is None


def test_one_local_date_survives_the_dst_change():
    before = datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc)
    after = datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc)
    nxt = datetime(2026, 3, 30, 0, 30, tzinfo=timezone.utc)
    assert company_local_date(before, "Europe/Madrid") == company_local_date(after, "Europe/Madrid")
    assert company_local_date(nxt, "Europe/Madrid") != company_local_date(before, "Europe/Madrid")


def test_a_manual_task_merges_only_through_an_explicit_link():
    signal = _cold()
    linked, loose = attach_manual(
        [signal],
        [
            {"remote_id": "task-1", "title": "Llamar a Marina", "linked_dedupe_key": signal.dedupe_key},
            {"remote_id": "task-2", "title": "Llamar a Marina"},
        ],
    )
    assert loose[0]["remote_id"] == "task-2"
    assert linked[0].payload["remote_id"] == "task-1"
    assert linked[0].payload["origins"] == ["detected", "manual"]

    partial = build_today_view(
        signals=[signal],
        manual_tasks=[{"remote_id": "task-2", "title": "Llamar a Marina"}],
        now=NOW,
        coverage={"intelligence": "complete", "crm_tasks": "partial"},
        generated_at="2026-09-22T08:00:00Z",
    )
    assert partial["pulse"] is None
    assert partial["coverage"]["crm_tasks"] == "partial"
    assert {item["remote_id"] for item in partial["items"]} == {None, "task-2"}

    complete = build_today_view(
        signals=[],
        manual_tasks=[],
        now=NOW,
        coverage={"intelligence": "complete", "crm_tasks": "complete"},
        generated_at="2026-09-22T08:00:00Z",
    )
    assert complete["pulse"] == 0
    assert complete["items"] == []


def test_resolving_identity_does_not_keep_two_rows():
    rows = [
        {"memo_id": "memo-1", "connection_id": "crm-A", "dedupe_key": "cold:memo-1", "contact_id": None},
        {"memo_id": "memo-1", "connection_id": "crm-A", "dedupe_key": "cold:memo-1", "contact_id": "42"},
    ]
    rebound = rebind_contact(rows, memo_id="memo-1", contact_id="42")
    assert rebound == [rows[1]]


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._filters = []

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def execute(self):
        rows = self._rows
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        return _Result(rows)


class _Supabase:
    def __init__(self):
        self.tables = {"action_signals": [], "crm_connections": []}

    @property
    def rows(self):
        return self.tables["action_signals"]

    @rows.setter
    def rows(self, value):
        self.tables["action_signals"] = value

    def table(self, name):
        return _Query(self.tables.setdefault(name, []))


STORE = _Supabase()


def test_today_reads_the_connected_crm_and_keeps_the_card_if_the_read_fails():
    STORE.rows = [{
        "company_id": "co-1",
        "user_id": "user-a",
        "status": "pending",
        "type": "going_cold",
        "contact_id": "42",
        "memo_id": "memo-1",
        "connection_id": "crm-A",
        "dedupe_key": "cold:42",
        "coverage": "complete",
        "payload": {"interest": "high", "days_silent": 12},
    }]
    STORE.tables["crm_connections"] = [{
        "id": "crm-A",
        "company_id": "co-1",
        "status": "connected",
        "provider": "hubspot",
        "access_token": "secret-token",
    }]

    def fetch(request):
        assert request["path"] == "/crm/v3/objects/tasks/search"
        assert request["json"]["filterGroups"][0]["filters"][0]["value"] == "COMPLETED"
        return {"results": [{
            "id": "7",
            "properties": {"hs_task_subject": "Llamar a Marina", "hs_task_status": "NOT_STARTED", "contact_id": "42"},
        }]}

    today_api.set_today_fetch(fetch)
    try:
        app = FastAPI()
        app.include_router(today_api.router)
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id="co-1", user_id="user-a", role="member", status="active",
        )
        app.dependency_overrides[get_supabase] = lambda: STORE
        client = TestClient(app)
        opened = client.get("/api/v1/today").json()
        today_api.set_today_fetch(lambda _request: (_ for _ in ()).throw(TimeoutError()))
        failed = client.get("/api/v1/today").json()
    finally:
        today_api.set_today_fetch(None)
        STORE.tables["crm_connections"] = []
    assert opened["coverage"]["crm_tasks"] == "complete"
    assert {item["remote_id"] for item in opened["items"]} == {None, "7"}
    assert "secret-token" not in str(opened)
    assert failed["coverage"]["crm_tasks"] == "unavailable"
    assert [item["dedupe_key"] for item in failed["items"]] == ["cold:42"]


def test_the_token_request_hits_hubspot_search_without_printing_the_token():
    import httpx

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["path"] = request.url.path
        return httpx.Response(200, json={"results": []})

    connection = {"provider": "hubspot", "access_token": "secret-token", "id": "crm-A"}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        page = today_api._http_task_page(connection, task_request("hubspot", None), client=client)
    assert seen["auth"] == "Bearer secret-token"
    assert seen["path"] == "/crm/v3/objects/tasks/search"
    assert page == {"results": []}
    tasks, coverage = collect_open_tasks("hubspot", lambda _request: page, connection_id="crm-A")
    assert tasks == []
    assert coverage == "complete"


def test_get_today_reason_follows_accept_language():
    STORE.rows = [{
        "company_id": "co-1",
        "user_id": "user-a",
        "status": "pending",
        "type": "going_cold",
        "contact_id": "42",
        "deal_id": None,
        "memo_id": "memo-1",
        "connection_id": "crm-A",
        "dedupe_key": "cold:42",
        "coverage": "complete",
        "payload": {"interest": "high", "days_silent": 12},
    }]
    today_api.set_today_tasks(lambda _company: ([], "complete"))
    try:
        client = _today_client()
        spanish = client.get("/api/v1/today").json()
        english = client.get("/api/v1/today", headers={"Accept-Language": "en"}).json()
    finally:
        today_api.set_today_tasks(None)
    signal = _cold()
    assert spanish["items"][0]["reason"] == reason(signal, lang="es")
    assert english["items"][0]["reason"] == reason(signal, lang="en")


def test_today_keeps_a_pending_card_when_crm_tasks_were_not_read():
    STORE.rows = [{
        "company_id": "co-1",
        "user_id": "user-a",
        "status": "pending",
        "type": "going_cold",
        "contact_id": "42",
        "deal_id": None,
        "memo_id": "memo-1",
        "connection_id": "crm-A",
        "dedupe_key": "cold:42",
        "id": "sig-1",
        "version": 4,
        "coverage": "complete",
        "payload": {"interest": "high", "days_silent": 12},
    }, {
        "company_id": "co-1",
        "user_id": "user-a",
        "status": "dismissed",
        "type": "going_cold",
        "dedupe_key": "cold:other",
        "payload": {"interest": "high", "days_silent": 12},
    }]
    app = FastAPI()
    app.include_router(today_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: STORE
    body = TestClient(app).get("/api/v1/today").json()
    assert [item["dedupe_key"] for item in body["items"]] == ["cold:42"]
    assert body["items"][0]["id"] == "sig-1"
    assert body["items"][0]["version"] == 4
    assert body["pulse"] is None
    assert body["coverage"]["crm_tasks"] == "unavailable"


def _pg_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def _psql(dsn: str, sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True, text=True, timeout=20, check=False, env=_pg_env(),
    )


def _start_postgres():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-hoy-day-"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    init = subprocess.run(
        [initdb, "-D", str(datadir), "--auth=trust", "--no-instructions", "-U", "vocify", "--encoding=UTF8", "--locale=C"],
        capture_output=True, text=True, check=False, env=_pg_env(),
    )
    if init.returncode != 0:
        shutil.rmtree(datadir, ignore_errors=True)
        pytest.skip(init.stderr[-300:])
    log_path = datadir / "pg.log"
    proc = subprocess.Popen(
        [postgres, "-D", str(datadir), "-p", str(port), "-h", "127.0.0.1", "-k", str(datadir)],
        stdout=log_path.open("w"), stderr=subprocess.STDOUT, env=_pg_env(),
    )
    dsn = f"postgresql://vocify@127.0.0.1:{port}/postgres"
    for _ in range(40):
        if proc.poll() is not None:
            shutil.rmtree(datadir, ignore_errors=True)
            pytest.skip((log_path.read_text() if log_path.exists() else "")[-300:])
        if _psql(dsn, "SELECT 1;").returncode == 0:
            return dsn, proc, datadir
        import time
        time.sleep(0.15)
    proc.terminate()
    shutil.rmtree(datadir, ignore_errors=True)
    pytest.skip("postgres no respondió")


def test_two_workers_claim_one_local_day():
    dsn, proc, datadir = _start_postgres()
    try:
        applied = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(MIGRATION)],
            capture_output=True, text=True, timeout=20, check=False, env=_pg_env(),
        )
        assert applied.returncode == 0, applied.stderr
        local_date = company_local_date(NOW, "Europe/Madrid")
        statement = claim_daily_run_statement(COMPANY, local_date)
        errors = []

        def write():
            result = _psql(dsn, statement)
            if result.returncode != 0:
                errors.append(result.stderr)

        threads = [threading.Thread(target=write) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        counted = _psql(dsn, "SELECT count(*) FROM hoy_daily_runs;")
        assert "1" in counted.stdout
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)
