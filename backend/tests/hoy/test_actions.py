"""F06: one request, one transition. Undo stops at five seconds and does not rewind a call."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-actions")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-actions")

import shutil
import socket
import subprocess
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import today as today_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.hoy.actions import apply_action, undo_action
from app.services.hoy.repository import transition_statement

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "043_action_signals.sql"
NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
COMPANY = "11111111-1111-1111-1111-111111111111"
USER = "22222222-2222-2222-2222-222222222222"
SIGNAL = "33333333-3333-3333-3333-333333333333"


def _row(version: int = 3) -> dict:
    return {
        "id": "sig-1",
        "company_id": "co-1",
        "user_id": "user-a",
        "status": "pending",
        "version": version,
        "previous_status": None,
        "last_action_request_id": None,
        "undo_deadline": None,
        "snoozed_until": None,
    }


def test_the_same_request_keeps_the_deadline_and_a_stale_version_conflicts():
    first = apply_action(
        _row(),
        action="dismiss",
        request_id="act-2",
        expected_version=3,
        until=None,
        now=NOW,
        user_id="user-a",
        company_id="co-1",
    )
    second = apply_action(
        first,
        action="resolve",
        request_id="act-2",
        expected_version=3,
        until=None,
        now=NOW + timedelta(seconds=4),
        user_id="user-a",
        company_id="co-1",
    )
    assert second["replayed"] is True
    assert second["version"] == 4
    assert second["undo_deadline"] == first["undo_deadline"]
    assert second["status"] == "dismissed"
    with pytest.raises(Exception) as conflict:
        apply_action(
            first,
            action="resolve",
            request_id="act-9",
            expected_version=3,
            until=None,
            now=NOW,
            user_id="user-a",
            company_id="co-1",
        )
    assert conflict.value.code == "conflict"
    assert conflict.value.row["status"] == "dismissed"


def test_undo_after_five_seconds_leaves_the_signal_and_does_not_name_a_call():
    acted = apply_action(
        _row(),
        action="dismiss",
        request_id="act-2",
        expected_version=3,
        until=None,
        now=NOW,
        user_id="user-a",
        company_id="co-1",
    )
    late = NOW + timedelta(seconds=6)
    with pytest.raises(Exception) as expired:
        undo_action(acted, request_id="act-2", expected_version=4, now=late, user_id="user-a", company_id="co-1")
    assert expired.value.code == "expired"
    assert expired.value.row["status"] == "dismissed"
    assert "call" not in expired.value.row
    restored = undo_action(
        acted,
        request_id="act-2",
        expected_version=4,
        now=NOW + timedelta(seconds=5),
        user_id="user-a",
        company_id="co-1",
    )
    assert restored["status"] == "pending"
    assert restored["version"] == 5
    assert restored["undo_deadline"] is None


class _Result:
    def __init__(self, data):
        self.data = data


class _Store:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        assert name == "action_signals"
        return _Query(self)


class _Query:
    def __init__(self, store, payload=None):
        self.store = store
        self.payload = payload
        self.filters = []

    def select(self, *_args, **_kwargs):
        return self

    def update(self, payload):
        return _Query(self.store, payload)

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        rows = self.store.rows
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        if self.payload is None:
            return _Result(rows)
        for row in rows:
            row.update(self.payload)
        return _Result(rows)


def test_http_replay_and_foreign_signal():
    row = {
        "id": "sig-1",
        "company_id": "co-1",
        "user_id": "user-a",
        "status": "pending",
        "version": 3,
        "previous_status": None,
        "last_action_request_id": None,
        "last_action_at": None,
        "undo_deadline": None,
        "snoozed_until": None,
    }
    store = _Store([row])
    today_api._CLOCK[0] = NOW
    app = FastAPI()
    app.include_router(today_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: store
    client = TestClient(app)
    body = {"action": "dismiss", "request_id": "act-2", "expected_version": 3, "until": None}
    first = client.post("/api/v1/today/sig-1/resolve", json=body)
    second = client.post("/api/v1/today/sig-1/resolve", json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["undo_deadline"] == second.json()["undo_deadline"]
    assert second.json()["version"] == 4
    stale = client.post("/api/v1/today/sig-1/resolve", json={**body, "request_id": "act-9", "action": "resolve"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["version"] == 4
    stranger = TestClient(app)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="user-b", role="member", status="active",
    )
    hidden = stranger.post("/api/v1/today/sig-1/resolve", json=body)
    assert hidden.status_code == 404


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


def test_two_transitions_of_the_same_version_leave_one_winner():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-hoy-act-"))
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
    try:
        for _ in range(40):
            if proc.poll() is not None:
                pytest.skip((log_path.read_text() if log_path.exists() else "")[-300:])
            if _psql(dsn, "SELECT 1;").returncode == 0:
                break
            import time
            time.sleep(0.15)
        applied = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(MIGRATION)],
            capture_output=True, text=True, timeout=20, check=False, env=_pg_env(),
        )
        assert applied.returncode == 0, applied.stderr
        inserted = _psql(
            dsn,
            "INSERT INTO action_signals (id, company_id, user_id, connection_id, type, dedupe_key, status, version) "
            f"VALUES ('{SIGNAL}', '{COMPANY}', '{USER}', 'crm-A', 'going_cold', 'cold:1', 'pending', 1);",
        )
        assert inserted.returncode == 0, inserted.stderr
        outputs = []

        def write(request_id: str):
            sql = transition_statement(
                signal_id=SIGNAL,
                company_id=COMPANY,
                user_id=USER,
                expected_version=1,
                request_id=request_id,
                status="dismissed",
            )
            outputs.append(_psql(dsn, sql).stdout)

        threads = [threading.Thread(target=write, args=(f"act-{index}",)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sum(1 for output in outputs if "UPDATE 1" in output) == 1
        version = _psql(dsn, "SELECT version::text FROM action_signals;")
        assert "2" in version.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)
