"""050 fills memos.company_id from the author's membership once; a set company stays immutable."""

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
UP = MIGRATIONS / "050_memos_company_backfill.sql"
DOWN = MIGRATIONS / "050_memos_company_backfill.down.sql"

SCHEMA = """
CREATE TABLE company_members (user_id UUID PRIMARY KEY, company_id UUID NOT NULL);
CREATE TABLE memos (id TEXT PRIMARY KEY, user_id UUID NOT NULL, company_id UUID, client_capture_id TEXT);
CREATE FUNCTION memos_lock_capture_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.company_id IS DISTINCT FROM OLD.company_id THEN
    RAISE EXCEPTION 'memos.company_id is immutable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER memos_lock_capture_identity BEFORE UPDATE ON memos
  FOR EACH ROW EXECUTE FUNCTION memos_lock_capture_identity();
INSERT INTO company_members VALUES
  ('00000000-0000-0000-0000-00000000000a', '11111111-1111-1111-1111-111111111111');
INSERT INTO memos (id, user_id, company_id) VALUES
  ('m-null', '00000000-0000-0000-0000-00000000000a', NULL),
  ('m-orphan', '00000000-0000-0000-0000-00000000000b', NULL),
  ('m-set', '00000000-0000-0000-0000-00000000000a', '22222222-2222-2222-2222-222222222222');
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
    datadir = Path(tempfile.mkdtemp(prefix="vocify-memo-company-pg-"))
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


def _company(url: str, memo_id: str) -> str:
    return _psql(url, "-c", f"SELECT coalesce(company_id::text, 'null') FROM memos WHERE id = '{memo_id}';").stdout.strip()


def test_backfill_fills_only_null_companies_and_keeps_set_ones_immutable(dsn):
    applied = _psql(dsn, "-f", str(UP))
    assert applied.returncode == 0, applied.stderr
    assert _company(dsn, "m-null") == "11111111-1111-1111-1111-111111111111"
    assert _company(dsn, "m-orphan") == "null"
    assert _company(dsn, "m-set") == "22222222-2222-2222-2222-222222222222"

    moved = _psql(dsn, "-c", "UPDATE memos SET company_id = '33333333-3333-3333-3333-333333333333' WHERE id = 'm-set';")
    assert moved.returncode != 0
    assert "immutable" in moved.stderr

    filled_later = _psql(dsn, "-c", "UPDATE memos SET company_id = '11111111-1111-1111-1111-111111111111' WHERE id = 'm-orphan';")
    assert filled_later.returncode == 0, filled_later.stderr


def test_rollback_restores_the_strict_trigger(dsn):
    assert _psql(dsn, "-f", str(UP)).returncode == 0
    rolled = _psql(dsn, "-f", str(DOWN))
    assert rolled.returncode == 0, rolled.stderr
    blocked = _psql(dsn, "-c", "UPDATE memos SET company_id = '11111111-1111-1111-1111-111111111111' WHERE id = 'm-orphan';")
    assert blocked.returncode != 0
    assert _company(dsn, "m-null") == "11111111-1111-1111-1111-111111111111"
