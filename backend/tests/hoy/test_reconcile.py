"""F05 reconcile: one signal, a dismissal stays, and a down source does not resolve."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-reconcile")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-reconcile")

import shutil
import socket
import subprocess
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.hoy.reconcile import merge_fresh, plan_reconcile
from app.services.hoy.repository import insert_signal_statement, reopen_statement
from app.services.hoy.signals import Signal

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "043_action_signals.sql"
COMPANY = "11111111-1111-1111-1111-111111111111"
USER = "22222222-2222-2222-2222-222222222222"
NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


def _signal(key: str = "cold:memo-1", text: str = "una", evidence: str = "ev-1") -> Signal:
    return Signal(
        type="going_cold",
        contact_id="42",
        deal_id="deal-7",
        source_memo_id="memo-1",
        due_at=None,
        payload={"interest": "high", "days_silent": 12, "text": text, "evidence_refs": [evidence]},
        dedupe_key=key,
        connection_id="crm-A",
    )


def test_same_key_keeps_every_commitment_and_dismissal_survives():
    merged = merge_fresh([_signal(text="enviar el caso", evidence="ev-1"), _signal(text="llamar el viernes", evidence="ev-2")])
    assert len(merged) == 1
    assert [item["text"] for item in merged[0].payload["items"]] == ["enviar el caso", "llamar el viernes"]
    assert merged[0].payload["items"][1]["evidence_refs"] == ["ev-2"]

    stored = [{"dedupe_key": "cold:memo-1", "status": "dismissed", "version": 4, "snoozed_until": None}]
    plan = plan_reconcile(stored=stored, fresh=[_signal()], now=NOW, source_available=True)
    assert plan["insert"] == []
    assert plan["reopen"] == []
    assert plan["resolve"] == []


def test_a_down_source_does_not_resolve_and_an_expired_snooze_reopens_only_if_it_still_applies():
    pending = [{"dedupe_key": "cold:memo-1", "status": "pending", "version": 1, "snoozed_until": None}]
    down = plan_reconcile(stored=pending, fresh=[], now=NOW, source_available=False)
    assert down["resolve"] == []
    assert down["insert"] == []

    snoozed = [{
        "dedupe_key": "cold:memo-1",
        "status": "snoozed",
        "version": 2,
        "snoozed_until": NOW - timedelta(hours=1),
    }]
    still = plan_reconcile(stored=snoozed, fresh=[_signal()], now=NOW, source_available=True)
    assert still["reopen"][0]["expected_version"] == 2
    assert still["resolve"] == []

    waiting = [{**snoozed[0], "snoozed_until": NOW + timedelta(days=1)}]
    held = plan_reconcile(stored=waiting, fresh=[_signal()], now=NOW, source_available=True)
    assert held["reopen"] == []

    gone = plan_reconcile(stored=snoozed, fresh=[], now=NOW, source_available=True)
    assert gone["resolve"] == ["cold:memo-1"]
    assert gone["reopen"] == []


def _pg_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def _psql(dsn: str, sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        env=_pg_env(),
    )


def _start_postgres():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-hoy-pg-"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    init = subprocess.run(
        [initdb, "-D", str(datadir), "--auth=trust", "--no-instructions", "-U", "vocify", "--encoding=UTF8", "--locale=C"],
        capture_output=True,
        text=True,
        check=False,
        env=_pg_env(),
    )
    if init.returncode != 0:
        shutil.rmtree(datadir, ignore_errors=True)
        pytest.skip(init.stderr[-300:])
    log_path = datadir / "pg.log"
    proc = subprocess.Popen(
        [postgres, "-D", str(datadir), "-p", str(port), "-h", "127.0.0.1", "-k", str(datadir)],
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
        env=_pg_env(),
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


def _stop(proc, datadir) -> None:
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    if datadir is not None:
        shutil.rmtree(datadir, ignore_errors=True)


def test_two_workers_insert_one_row_and_only_one_reopen_wins():
    dsn, proc, datadir = _start_postgres()
    try:
        applied = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(MIGRATION)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=_pg_env(),
        )
        assert applied.returncode == 0, applied.stderr
        statement = insert_signal_statement(company_id=COMPANY, user_id=USER, signal=_signal())
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
        counted = _psql(dsn, "SELECT count(*) FROM action_signals;")
        assert "1" in counted.stdout
        marked = _psql(dsn, "UPDATE action_signals SET status = 'snoozed', version = 1, snoozed_until = now() - interval '1 hour';")
        assert marked.returncode == 0
        change = {"dedupe_key": "cold:memo-1", "expected_version": 1, "version": 2, "payload": {"interest": "high"}}
        reopen = reopen_statement(company_id=COMPANY, user_id=USER, connection_id="crm-A", change=change)
        winners = []

        def race():
            result = _psql(dsn, reopen)
            winners.append(result.stdout)

        racers = [threading.Thread(target=race) for _ in range(2)]
        for racer in racers:
            racer.start()
        for racer in racers:
            racer.join()
        assert sum(1 for output in winners if "UPDATE 1" in output) == 1
        version = _psql(dsn, "SELECT version::text || ' ' || status FROM action_signals;")
        assert "2 pending" in version.stdout
    finally:
        _stop(proc, datadir)
