"""A real PostgreSQL for the tests that need one (the playbooks SQL functions and migration).

Where the server comes from, in order:
  1. VOCIFY_TEST_PG_DSN: the DSN of a running server whose role can CREATE DATABASE, for example
     `postgresql://vocify@127.0.0.1:5432/postgres`. Use it where PostgreSQL will not start inside the test
     process (it refuses to run as root): start a cluster as another user and point the variable at it.
  2. Otherwise a throwaway cluster is initialised in a temp directory and started, as the other
     "PostgreSQL aislado" tests do. Not possible as root: the tests are then skipped.
  3. No initdb/postgres/psql on the machine: skipped ("No hay PostgreSQL aislado").

Every test gets its own database, cloned from a template that already has the playbooks schema
(migrations 040, 055 and 066_playbooks_v2), so tests never see each other's rows.

`PgClient` is the one thing the SQL repository needs from a Supabase client: `rpc(name, params).execute().data`.
It runs the call through `psql`, so no database driver is required.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import pytest

ENV_DSN = "VOCIFY_TEST_PG_DSN"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
SCHEMA_FILES = ("040_company_playbooks.sql", "055_playbook_goal.sql", "066_playbooks_v2.sql", "076_type_recognize.sql")


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def psql(dsn: str, sql: str, *, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["psql", dsn, "-q", "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql],
        capture_output=True, text=True, timeout=timeout, check=False, env=_env(),
    )


def psql_file(dsn: str, path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["psql", dsn, "-q", "-v", "ON_ERROR_STOP=1", "-f", str(path)],
        capture_output=True, text=True, timeout=120, check=False, env=_env(),
    )


class RpcError(Exception):
    """What supabase-py raises for a failed rpc (postgrest APIError): `message` is the RAISE EXCEPTION text."""

    def __init__(self, message: str, code: str = "P0001"):
        super().__init__({"message": message, "code": code})
        self.message = message
        self.code = code


class _Result:
    def __init__(self, data: Any):
        self.data = data


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return "'" + str(value).replace("'", "''") + "'"


class PgClient:
    """`rpc(name, params).execute().data` over psql. Anything else of the Supabase client is not here on
    purpose: the repository under test only calls SQL functions."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.calls: list[tuple[str, dict]] = []

    def rpc(self, name: str, params: Optional[dict] = None):
        params = dict(params or {})
        client = self

        class _Call:
            def execute(self) -> _Result:
                client.calls.append((name, params))
                args = ", ".join(f"{key} => {_literal(value)}" for key, value in params.items())
                done = psql(client.dsn, f"SELECT to_jsonb({name}({args}));")
                if done.returncode != 0:
                    match = re.search(r"ERROR:\s+(.*)", done.stderr)
                    raise RpcError(match.group(1).strip() if match else done.stderr.strip())
                out = done.stdout.strip()
                return _Result(json.loads(out) if out else None)

        return _Call()

    def sql(self, text: str) -> str:
        """Runs one statement, returns its output (`-tA`), raises AssertionError on failure."""
        done = psql(self.dsn, text)
        assert done.returncode == 0, done.stderr
        return done.stdout.strip()


class Cluster:
    def __init__(self, admin_dsn: str, cleanup=None):
        self.admin_dsn = admin_dsn
        self._cleanup = cleanup
        self.template = f"vocify_tpl_{uuid.uuid4().hex[:10]}"

    def dsn_for(self, database: str) -> str:
        # postgresql://user@host:port/db -> same server, other database
        return re.sub(r"/[^/?]*(\?.*)?$", lambda m: f"/{database}{m.group(1) or ''}", self.admin_dsn)

    def create_database(self, template: Optional[str] = None) -> str:
        name = f"vocify_t_{uuid.uuid4().hex[:12]}"
        clause = f' TEMPLATE "{template}"' if template else ""
        done = psql(self.admin_dsn, f'CREATE DATABASE "{name}"{clause};')
        assert done.returncode == 0, done.stderr
        return name

    def drop_database(self, name: str) -> None:
        psql(self.admin_dsn, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE);')

    def build_template(self) -> None:
        done = psql(self.admin_dsn, f'CREATE DATABASE "{self.template}";')
        assert done.returncode == 0, done.stderr
        dsn = self.dsn_for(self.template)
        for name in SCHEMA_FILES:
            applied = psql_file(dsn, MIGRATIONS / name)
            assert applied.returncode == 0, f"{name}: {applied.stderr}"

    def close(self) -> None:
        psql(self.admin_dsn, f'DROP DATABASE IF EXISTS "{self.template}" WITH (FORCE);')
        if self._cleanup:
            self._cleanup()


def start_cluster() -> Optional[Cluster]:
    """A Cluster, or None (then the caller skips) when no PostgreSQL can be had."""
    given = os.environ.get(ENV_DSN, "").strip()
    if given:
        if not shutil.which("psql"):
            return None
        probe = psql(given, "SELECT 1;")
        if probe.returncode != 0:
            pytest.fail(f"{ENV_DSN} is set but PostgreSQL does not answer: {probe.stderr.strip()}")
        return Cluster(given)
    initdb, postgres = shutil.which("initdb"), shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        return None
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return None  # PostgreSQL will not start as root: set VOCIFY_TEST_PG_DSN to a server started as another user
    datadir = Path(tempfile.mkdtemp(prefix="vocify-pb-"))
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
        return None
    log = (datadir / "pg.log").open("w")
    proc = subprocess.Popen(
        [postgres, "-D", str(datadir), "-p", str(port), "-h", "127.0.0.1", "-k", str(datadir)],
        stdout=log, stderr=subprocess.STDOUT, env=_env(),
    )
    dsn = f"postgresql://vocify@127.0.0.1:{port}/postgres"

    def cleanup() -> None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        shutil.rmtree(datadir, ignore_errors=True)

    for _ in range(80):
        if proc.poll() is not None:
            cleanup()
            return None
        if psql(dsn, "SELECT 1;").returncode == 0:
            return Cluster(dsn, cleanup)
        time.sleep(0.15)
    cleanup()
    return None
