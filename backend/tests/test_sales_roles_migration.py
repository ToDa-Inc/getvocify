"""055 adds sales_role to company_members and company_invitations; default is general."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
UP = MIGRATIONS / "055_sales_roles.sql"
DOWN = MIGRATIONS / "055_sales_roles.down.sql"

CO = "11111111-1111-1111-1111-111111111111"
USER = "22222222-2222-2222-2222-222222222222"

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE company_members (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  company_id UUID NOT NULL,
  user_id UUID NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id),
  UNIQUE (company_id, user_id)
);

CREATE TABLE company_invitations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  company_id UUID NOT NULL,
  email CITEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
  token_hash TEXT NOT NULL,
  invited_by UUID,
  expires_at TIMESTAMPTZ NOT NULL,
  accepted_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO company_members (company_id, user_id, role)
VALUES ('{CO}', '{USER}', 'owner');

INSERT INTO company_invitations (company_id, email, role, token_hash, expires_at)
VALUES ('{CO}', 'a@example.com', 'member', 'hash', NOW() + INTERVAL '1 day');
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
    datadir = Path(tempfile.mkdtemp(prefix="vocify-sales-roles-pg-"))
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


def _columns(url: str, table: str) -> set[str]:
    out = _psql(
        url, "-c",
        f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}';",
    )
    return set(out.stdout.split())


def test_sales_role_defaults_to_general_and_is_idempotent(dsn):
    for _ in range(2):
        applied = _psql(dsn, "-f", str(UP))
        assert applied.returncode == 0, applied.stderr
    assert "sales_role" in _columns(dsn, "company_members")
    assert "sales_role" in _columns(dsn, "company_invitations")
    member = _psql(dsn, "-c", "SELECT sales_role FROM company_members LIMIT 1;")
    assert member.stdout.strip() == "general"
    invite = _psql(dsn, "-c", "SELECT sales_role FROM company_invitations LIMIT 1;")
    assert invite.stdout.strip() == "general"
    bad = _psql(dsn, "-c", "UPDATE company_members SET sales_role = 'nope';")
    assert bad.returncode != 0


def test_rollback_removes_sales_role(dsn):
    assert _psql(dsn, "-f", str(UP)).returncode == 0
    rolled = _psql(dsn, "-f", str(DOWN))
    assert rolled.returncode == 0, rolled.stderr
    assert "sales_role" not in _columns(dsn, "company_members")
    assert "sales_role" not in _columns(dsn, "company_invitations")
    assert _psql(dsn, "-f", str(DOWN)).returncode == 0
