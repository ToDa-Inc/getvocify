"""054 adds queue exit state columns; backfill copies meeting_booked_stage_id."""

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
UP = MIGRATIONS / "054_crm_queue_states.sql"
DOWN = MIGRATIONS / "054_crm_queue_states.down.sql"

SCHEMA = """
CREATE TABLE crm_configurations (
  id TEXT PRIMARY KEY,
  connection_id TEXT UNIQUE NOT NULL,
  default_stage_id TEXT NOT NULL,
  meeting_booked_pipeline_id TEXT,
  meeting_booked_stage_id TEXT
);
INSERT INTO crm_configurations VALUES ('c-1', 'conn-1', 'new', 'default', 'appointmentscheduled');
INSERT INTO crm_configurations VALUES ('c-2', 'conn-2', 'new', NULL, NULL);
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
    datadir = Path(tempfile.mkdtemp(prefix="vocify-queue-states-pg-"))
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


def _columns(url: str) -> set[str]:
    out = _psql(url, "-c", "SELECT column_name FROM information_schema.columns WHERE table_name = 'crm_configurations';")
    return set(out.stdout.split())


def test_queue_state_columns_backfill_and_are_idempotent(dsn):
    for _ in range(2):
        applied = _psql(dsn, "-f", str(UP))
        assert applied.returncode == 0, applied.stderr
    assert {"queue_state_source", "queue_booked_states", "queue_ended_states"} <= _columns(dsn)
    booked = _psql(
        dsn, "-c",
        "SELECT array_to_string(queue_booked_states, ',') FROM crm_configurations WHERE id = 'c-1';",
    )
    assert booked.stdout.strip() == "appointmentscheduled"
    empty = _psql(
        dsn, "-c",
        "SELECT coalesce(array_length(queue_booked_states, 1), 0) FROM crm_configurations WHERE id = 'c-2';",
    )
    assert empty.stdout.strip() == "0"
    bad = _psql(dsn, "-c", "UPDATE crm_configurations SET queue_state_source = 'nope' WHERE id = 'c-1';")
    assert bad.returncode != 0


def test_rollback_removes_queue_state_columns(dsn):
    assert _psql(dsn, "-f", str(UP)).returncode == 0
    rolled = _psql(dsn, "-f", str(DOWN))
    assert rolled.returncode == 0, rolled.stderr
    assert not {"queue_state_source", "queue_booked_states", "queue_ended_states"} & _columns(dsn)
    assert _psql(dsn, "-f", str(DOWN)).returncode == 0
