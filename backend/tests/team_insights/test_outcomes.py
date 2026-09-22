"""F15: one deal is one team win. EUR and USD stay apart. History is not rewritten."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-team-32bytes+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-32bytes+")

import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.services.team_insights.outcomes import (
    amounts_by_currency,
    insert_observation_statement,
    observe_deal,
    reconcile_wins,
    record_observation,
)

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "049_team_outcomes.sql"
COMPANY = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_two_owners_without_a_primary_count_once_as_unresolved():
    observation = observe_deal(
        connection_id="crm-A",
        deal_id="deal-7",
        status="won",
        owners=[{"user_id": "user-a", "primary": False}, {"user_id": "user-b", "primary": False}],
        amount="1200.00",
        currency="EUR",
        closed_at="2026-09-20T00:00:00Z",
        observed_at="2026-09-22T12:00:00Z",
    )
    assert observation["owner_user_id"] is None
    assert observation["attribution"] == "unresolved"
    assert observation["previous_status"] is None
    totals = reconcile_wins([observation, observation])
    assert totals == {"won_deals": 1, "assigned": 0, "unresolved": 1}


def test_an_owner_change_appends_and_currencies_are_not_added():
    first = observe_deal(
        connection_id="crm-A", deal_id="deal-7", status="won",
        owners=[{"user_id": "22222222-2222-2222-2222-222222222222", "primary": True}],
        amount="1200.00", currency="EUR", closed_at="2026-09-20T00:00:00Z", observed_at="2026-09-22T12:00:00Z",
    )
    second = observe_deal(
        connection_id="crm-A", deal_id="deal-7", status="open",
        owners=[{"user_id": "33333333-3333-3333-3333-333333333333", "primary": True}],
        amount="1200.00", currency="EUR", closed_at=None, observed_at="2026-09-23T12:00:00Z",
    )
    dollars = observe_deal(
        connection_id="crm-A", deal_id="deal-8", status="won",
        owners=[{"user_id": "22222222-2222-2222-2222-222222222222", "primary": True}],
        amount="50.00", currency="USD", closed_at="2026-09-21T00:00:00Z", observed_at="2026-09-22T12:00:00Z",
    )
    report = {"id": "report-1", "deals_won": 1}
    history = record_observation([], first, report)
    history = record_observation(history, second, report)
    assert report == {"id": "report-1", "deals_won": 1}
    assert len(history) == 2
    assert reconcile_wins(history)["won_deals"] == 0
    assert amounts_by_currency([first, dollars]) == {"EUR": "1200.00", "USD": "50.00"}


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


def test_postgres_keeps_two_observations_of_the_same_deal():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-team-"))
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
        first = observe_deal(
            connection_id="crm-A", deal_id="deal-7", status="won",
            owners=[{"user_id": "22222222-2222-2222-2222-222222222222", "primary": True}],
            amount="1200.00", currency="EUR", closed_at="2026-09-20T00:00:00Z", observed_at="2026-09-22T12:00:00Z",
        )
        later = {**first, "observed_at": "2026-09-23T12:00:00Z", "status": "open", "owner_user_id": "33333333-3333-3333-3333-333333333333"}
        assert _psql(dsn, insert_observation_statement(company_id=COMPANY, observation=first)).returncode == 0
        assert _psql(dsn, insert_observation_statement(company_id=COMPANY, observation=first)).returncode == 0
        assert _psql(dsn, insert_observation_statement(company_id=COMPANY, observation=later)).returncode == 0
        counted = _psql(dsn, "SELECT count(*) FROM team_outcome_observations;")
        assert "2" in counted.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)
