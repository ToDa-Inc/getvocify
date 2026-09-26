"""053: report opt-outs are service-role only, and old meeting writes keep an unknown time instead of an invented one."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
UP = MIGRATIONS / "053_reports_weekly_preferences.sql"
DOWN = MIGRATIONS / "053_reports_weekly_preferences.down.sql"

USER = "11111111-1111-1111-1111-111111111111"
MEMO = "22222222-2222-2222-2222-222222222222"

SCHEMA = f"""
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
GRANT USAGE ON SCHEMA public TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
CREATE TABLE meeting_writes (
  operation_key TEXT PRIMARY KEY,
  memo_id UUID NOT NULL,
  proposal_id TEXT NOT NULL,
  remote_id TEXT,
  crm_status TEXT NOT NULL,
  stage_changed BOOLEAN NOT NULL DEFAULT false
);
INSERT INTO meeting_writes VALUES ('old', '{MEMO}', 'p-1', 'r-1', 'succeeded', true);
"""


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def _psql(dsn: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-tA", *args],
        capture_output=True, text=True, timeout=20, check=False, env=_env(),
    )


@pytest.fixture
def dsn():
    initdb, postgres = shutil.which("initdb"), shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-report-prefs-pg-"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    init = subprocess.run(
        [initdb, "-D", str(datadir), "--auth=trust", "--no-instructions", "-U", "vocify", "--encoding=UTF8", "--locale=C"],
        capture_output=True, text=True, check=False, env=_env(),
    )
    if init.returncode != 0:
        shutil.rmtree(datadir, ignore_errors=True)
        pytest.skip(init.stderr[-300:])
    log = (datadir / "pg.log").open("w")
    proc = subprocess.Popen(
        [postgres, "-D", str(datadir), "-p", str(port), "-h", "127.0.0.1", "-k", str(datadir)],
        stdout=log, stderr=subprocess.STDOUT, env=_env(),
    )
    url = f"postgresql://vocify@127.0.0.1:{port}/postgres"
    for _ in range(40):
        if _psql(url, "-c", "SELECT 1;").returncode == 0:
            break
        time.sleep(0.15)
    try:
        assert _psql(url, "-c", SCHEMA).returncode == 0
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)


def _up(dsn: str) -> None:
    applied = _psql(dsn, "-f", str(UP))
    assert applied.returncode == 0, applied.stderr


def test_a_new_row_defaults_to_every_report_on_and_one_row_per_person(dsn):
    _up(dsn)
    assert _psql(dsn, "-c", f"INSERT INTO report_preferences (user_id) VALUES ('{USER}');").returncode == 0
    assert _psql(dsn, "-c", "SELECT daily_enabled, weekly_enabled, team_enabled FROM report_preferences;").stdout.strip() == "t|t|t"
    assert _psql(dsn, "-c", f"INSERT INTO report_preferences (user_id) VALUES ('{USER}');").returncode != 0
    assert _psql(dsn, "-c", f"UPDATE report_preferences SET weekly_enabled = NULL WHERE user_id = '{USER}';").returncode != 0


def test_old_meeting_writes_keep_an_unknown_time_and_new_ones_get_now(dsn):
    _up(dsn)
    assert _psql(dsn, "-c", "SELECT created_at IS NULL FROM meeting_writes WHERE operation_key = 'old';").stdout.strip() == "t"
    assert _psql(
        dsn, "-c",
        f"INSERT INTO meeting_writes (operation_key, memo_id, proposal_id, crm_status, stage_changed) "
        f"VALUES ('new', '{MEMO}', 'p-2', 'succeeded', true);",
    ).returncode == 0
    assert _psql(dsn, "-c", "SELECT created_at IS NOT NULL FROM meeting_writes WHERE operation_key = 'new';").stdout.strip() == "t"


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_clients_can_neither_read_nor_write_preferences(dsn, role):
    _up(dsn)
    rls = _psql(dsn, "-c", "SELECT relrowsecurity FROM pg_class WHERE relname = 'report_preferences';")
    assert rls.stdout.strip() == "t"
    for statement in (
        "SELECT * FROM report_preferences;",
        f"INSERT INTO report_preferences (user_id) VALUES ('{USER}');",
        "UPDATE report_preferences SET daily_enabled = false;",
        "DELETE FROM report_preferences;",
    ):
        denied = _psql(dsn, "-c", f"SET ROLE {role}; {statement}")
        assert denied.returncode != 0, statement
        assert "permission denied" in denied.stderr


def test_rollback_restores_the_previous_shape_and_up_applies_twice(dsn):
    _up(dsn)
    rolled = _psql(dsn, "-f", str(DOWN))
    assert rolled.returncode == 0, rolled.stderr
    assert _psql(dsn, "-c", "SELECT to_regclass('public.report_preferences') IS NULL;").stdout.strip() == "t"
    column = _psql(
        dsn, "-c",
        "SELECT count(*) FROM information_schema.columns WHERE table_name = 'meeting_writes' AND column_name = 'created_at';",
    )
    assert column.stdout.strip() == "0"
    assert _psql(dsn, "-c", "SELECT count(*) FROM meeting_writes;").stdout.strip() == "1"
    _up(dsn)
    _up(dsn)
    assert _psql(dsn, "-c", "SELECT created_at IS NULL FROM meeting_writes WHERE operation_key = 'old';").stdout.strip() == "t"
