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
    company_local_date,
    rebind_contact,
)
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
        self.rows = []

    def table(self, name):
        assert name == "action_signals"
        return _Query(self.rows)


STORE = _Supabase()


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
