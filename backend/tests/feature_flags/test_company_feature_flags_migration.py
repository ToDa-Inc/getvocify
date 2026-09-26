"""051 stores per-company overrides of global switches. Only the service role reads or writes them."""

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
UP = MIGRATIONS / "051_company_feature_flags.sql"
DOWN = MIGRATIONS / "051_company_feature_flags.down.sql"

CO_A = "11111111-1111-1111-1111-111111111111"
CO_B = "22222222-2222-2222-2222-222222222222"

SCHEMA = f"""
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
GRANT USAGE ON SCHEMA public TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
CREATE TABLE companies (id UUID PRIMARY KEY, name TEXT NOT NULL);
INSERT INTO companies VALUES ('{CO_A}', 'Beta'), ('{CO_B}', 'Other');
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
    datadir = Path(tempfile.mkdtemp(prefix="vocify-feature-flags-pg-"))
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


def _set(dsn: str, company: str, flag: str, enabled: str) -> subprocess.CompletedProcess[str]:
    return _psql(
        dsn, "-c",
        f"INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES ('{company}', '{flag}', {enabled}) "
        "ON CONFLICT (company_id, flag) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now();",
    )


def _flags(dsn: str) -> str:
    return _psql(
        dsn, "-c", "SELECT company_id || ':' || flag || ':' || enabled FROM company_feature_flags ORDER BY 1;",
    ).stdout.strip()


def test_one_override_per_company_and_flag(dsn):
    _up(dsn)
    assert _set(dsn, CO_A, "INTELLIGENCE_EXTRACT_ENABLED", "true").returncode == 0
    assert _set(dsn, CO_A, "INTELLIGENCE_EXTRACT_ENABLED", "false").returncode == 0
    assert _set(dsn, CO_B, "INTELLIGENCE_EXTRACT_ENABLED", "true").returncode == 0
    assert _flags(dsn).splitlines() == [
        f"{CO_A}:INTELLIGENCE_EXTRACT_ENABLED:false",
        f"{CO_B}:INTELLIGENCE_EXTRACT_ENABLED:true",
    ]


def test_rejects_unknown_company_null_value_and_malformed_flag_names(dsn):
    _up(dsn)
    assert _set(dsn, "33333333-3333-3333-3333-333333333333", "INTELLIGENCE_EXTRACT_ENABLED", "true").returncode != 0
    assert _set(dsn, CO_A, "INTELLIGENCE_EXTRACT_ENABLED", "NULL").returncode != 0
    assert _set(dsn, CO_A, "intelligence_extract_enabled", "true").returncode != 0
    assert _set(dsn, CO_A, "", "true").returncode != 0
    assert _flags(dsn) == ""


def test_deleting_a_company_removes_its_overrides(dsn):
    _up(dsn)
    assert _set(dsn, CO_A, "INTELLIGENCE_EXTRACT_ENABLED", "true").returncode == 0
    assert _psql(dsn, "-c", f"DELETE FROM companies WHERE id = '{CO_A}';").returncode == 0
    assert _flags(dsn) == ""


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_clients_can_neither_read_nor_write(dsn, role):
    _up(dsn)
    assert _set(dsn, CO_A, "INTELLIGENCE_EXTRACT_ENABLED", "true").returncode == 0
    rls = _psql(dsn, "-c", "SELECT relrowsecurity FROM pg_class WHERE relname = 'company_feature_flags';")
    assert rls.stdout.strip() == "t"
    for statement in (
        "SELECT * FROM company_feature_flags;",
        f"INSERT INTO company_feature_flags (company_id, flag, enabled) VALUES ('{CO_B}', 'X', true);",
        "UPDATE company_feature_flags SET enabled = false;",
        "DELETE FROM company_feature_flags;",
    ):
        denied = _psql(dsn, "-c", f"SET ROLE {role}; {statement}")
        assert denied.returncode != 0, statement
        assert "permission denied" in denied.stderr
    assert _flags(dsn) == f"{CO_A}:INTELLIGENCE_EXTRACT_ENABLED:true"


def test_rollback_drops_the_table_and_up_applies_again(dsn):
    _up(dsn)
    assert _set(dsn, CO_A, "INTELLIGENCE_EXTRACT_ENABLED", "true").returncode == 0
    rolled = _psql(dsn, "-f", str(DOWN))
    assert rolled.returncode == 0, rolled.stderr
    gone = _psql(dsn, "-c", "SELECT to_regclass('public.company_feature_flags') IS NULL;")
    assert gone.stdout.strip() == "t"
    assert _psql(dsn, "-c", "SELECT count(*) FROM companies;").stdout.strip() == "2"
    _up(dsn)
    _up(dsn)
    assert _flags(dsn) == ""
