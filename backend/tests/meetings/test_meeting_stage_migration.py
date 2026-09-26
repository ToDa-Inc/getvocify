"""052 adds an opt-in meeting-booked stage per CRM configuration; empty means no stage moves."""

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
UP = MIGRATIONS / "052_crm_meeting_booked_stage.sql"
DOWN = MIGRATIONS / "052_crm_meeting_booked_stage.down.sql"

SCHEMA = """
CREATE TABLE crm_configurations (id TEXT PRIMARY KEY, connection_id TEXT UNIQUE NOT NULL, default_stage_id TEXT NOT NULL);
INSERT INTO crm_configurations VALUES ('c-1', 'conn-1', 'new');
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
    datadir = Path(tempfile.mkdtemp(prefix="vocify-meeting-stage-pg-"))
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


def test_existing_configurations_stay_without_a_stage_and_a_stage_needs_its_pipeline(dsn):
    for _ in range(2):
        applied = _psql(dsn, "-f", str(UP))
        assert applied.returncode == 0, applied.stderr
    assert {"meeting_booked_pipeline_id", "meeting_booked_stage_id"} <= _columns(dsn)
    kept = _psql(dsn, "-c", "SELECT coalesce(meeting_booked_stage_id, 'null') FROM crm_configurations WHERE id = 'c-1';")
    assert kept.stdout.strip() == "null"

    orphan = _psql(dsn, "-c", "UPDATE crm_configurations SET meeting_booked_stage_id = 'meeting' WHERE id = 'c-1';")
    assert orphan.returncode != 0

    mapped = _psql(
        dsn, "-c",
        "UPDATE crm_configurations SET meeting_booked_pipeline_id = 'default', meeting_booked_stage_id = 'meeting' WHERE id = 'c-1';",
    )
    assert mapped.returncode == 0, mapped.stderr


def test_rollback_removes_the_mapping(dsn):
    assert _psql(dsn, "-f", str(UP)).returncode == 0
    rolled = _psql(dsn, "-f", str(DOWN))
    assert rolled.returncode == 0, rolled.stderr
    assert not {"meeting_booked_pipeline_id", "meeting_booked_stage_id"} & _columns(dsn)
    assert _psql(dsn, "-f", str(DOWN)).returncode == 0
    assert _psql(dsn, "-c", "SELECT count(*) FROM crm_configurations;").stdout.strip() == "1"
