"""F0 jobs: one claim, a dead lease cannot publish, an older revision cannot replace a newer one."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-intelligence-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-intelligence-32")

import re
import shutil
import socket
import subprocess
import tempfile
import threading
from pathlib import Path

import pytest

from app.services.intelligence.revisions import input_revision

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "039_memo_intelligence_jobs.sql"


def _pg_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def _psql(dsn: str, sql: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=_pg_env(),
    )


def _psql_file(dsn: str, path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(path)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        env=_pg_env(),
    )


def _start_postgres():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres:
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-jobs-pg-"))
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
            pytest.skip("postgres no arrancó")
        if _psql(dsn, "SELECT 1;").returncode == 0:
            return dsn, proc, datadir
        import time
        time.sleep(0.15)
    proc.terminate()
    shutil.rmtree(datadir, ignore_errors=True)
    pytest.skip("postgres no respondió")


def _stop(proc, datadir):
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    if datadir is not None:
        shutil.rmtree(datadir, ignore_errors=True)


def _apply(dsn: str) -> None:
    assert MIGRATION.is_file()
    applied = _psql_file(dsn, MIGRATION)
    assert applied.returncode == 0, applied.stderr


def test_input_revision_ignores_updated_at_and_changes_with_notes():
    base = dict(schema="c04", extraction_revision="ext-1", notes_revision=None, identity="contact-1")
    first = input_revision(**base)
    same = input_revision(**base)
    changed = input_revision(**{**base, "notes_revision": "note-2"})
    assert first == same
    assert first != changed


def test_two_workers_one_claim_and_stale_publish_and_older_revision():
    dsn, proc, datadir = _start_postgres()
    try:
        _apply(dsn)
        inserted = _psql(
            dsn,
            """
            INSERT INTO memo_jobs (memo_id, kind, input_revision, revision_seq)
            VALUES ('11111111-1111-1111-1111-111111111111', 'intelligence', 'rev-a', 1);
            """,
        )
        assert inserted.returncode == 0, inserted.stderr

        errors: list[str] = []
        outputs: list[str] = []
        barrier = threading.Barrier(2)

        def claim_once() -> None:
            barrier.wait(timeout=5)
            result = _psql(
                dsn,
                "BEGIN; SELECT * FROM claim_memo_job('intelligence', 30); SELECT pg_sleep(1.2); COMMIT;",
                timeout=15,
            )
            outputs.append(result.stdout)
            if result.returncode != 0:
                errors.append(result.stderr)

        threads = [threading.Thread(target=claim_once), threading.Thread(target=claim_once)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        assert not errors, errors
        winners = [text for text in outputs if "rev-a" in text]
        assert len(winners) == 1

        expired = _psql(
            dsn,
            """
            UPDATE memo_jobs SET lease_until = now() - interval '1 second' WHERE revision_seq = 1;
            """,
        )
        assert expired.returncode == 0, expired.stderr
        run = _psql(dsn, "SELECT run_id::text FROM memo_jobs WHERE revision_seq = 1;")
        assert run.returncode == 0, run.stderr
        old_run = re.findall(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            run.stdout,
        )
        assert old_run, run.stdout
        rejected = _psql(
            dsn,
            f"SELECT publish_memo_job(id, '{old_run[0]}'::uuid, '{{\"value\": \"stale\"}}'::jsonb) FROM memo_jobs WHERE revision_seq = 1;",
        )
        assert "rejected" in rejected.stdout, rejected.stdout + rejected.stderr
        closed = _psql(
            dsn,
            "UPDATE memo_jobs SET status = 'failed' WHERE memo_id = '11111111-1111-1111-1111-111111111111';",
        )
        assert closed.returncode == 0, closed.stderr

        ordered = _psql(
            dsn,
            """
            INSERT INTO memo_jobs (memo_id, kind, input_revision, revision_seq)
            VALUES
              ('22222222-2222-2222-2222-222222222222', 'intelligence', 'rev-a', 1),
              ('22222222-2222-2222-2222-222222222222', 'intelligence', 'rev-b', 2);
            """,
        )
        assert ordered.returncode == 0, ordered.stderr
        claim_a = _psql(dsn, "SELECT * FROM claim_memo_job('intelligence', 60);")
        claim_b = _psql(dsn, "SELECT * FROM claim_memo_job('intelligence', 60);")
        assert "(1 row)" in claim_a.stdout and "(1 row)" in claim_b.stdout
        published_b = _psql(
            dsn,
            """
            SELECT publish_memo_job(id, run_id, '{"kept":"B"}'::jsonb)
            FROM memo_jobs
            WHERE memo_id = '22222222-2222-2222-2222-222222222222' AND revision_seq = 2;
            """,
        )
        assert "success" in published_b.stdout, published_b.stdout + published_b.stderr
        late_a = _psql(
            dsn,
            """
            SELECT publish_memo_job(id, run_id, '{"kept":"A"}'::jsonb), status
            FROM memo_jobs
            WHERE memo_id = '22222222-2222-2222-2222-222222222222' AND revision_seq = 1;
            """,
        )
        assert late_a.returncode == 0, late_a.stderr
        assert "rejected" in late_a.stdout or "superseded" in late_a.stdout
        assert "superseded" in late_a.stdout
        current = _psql(
            dsn,
            """
            SELECT result->>'kept' FROM memo_jobs
            WHERE memo_id = '22222222-2222-2222-2222-222222222222' AND revision_seq = 2;
            """,
        )
        assert "B" in current.stdout
        assert "A" not in current.stdout
    finally:
        _stop(proc, datadir)
