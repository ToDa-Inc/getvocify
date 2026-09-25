"""F14 writes: one approval, one activity. A timeout is reconciled before another create."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-meetings-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-meetings-32")

import shutil
import socket
import subprocess
import tempfile
import threading
from pathlib import Path

import pytest

from app.services.meetings.writes import MeetingWriteError, insert_write_statement, register_meeting, with_meeting

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "046_meeting_proposals.sql"
MEMO = "66666666-6666-6666-6666-666666666666"


class Writer:
    def __init__(self, fail_once: bool = False):
        self.created = []
        self.stages = []
        self.remote = {}
        self.fail_once = fail_once

    def create(self, operation_key: str, proposal: dict) -> str:
        del proposal
        if self.fail_once:
            self.fail_once = False
            self.remote[operation_key] = "act-1"
            raise TimeoutError("crm")
        self.created.append(operation_key)
        self.remote[operation_key] = "act-1"
        return "act-1"

    def reconcile(self, operation_key: str):
        return self.remote.get(operation_key)

    def change_stage(self, mapping: str) -> None:
        self.stages.append(mapping)


def _proposal():
    return {
        "proposal_id": "meet-1",
        "agreement": "agreed",
        "starts_at": "2026-09-29T15:00:00+00:00",
        "timezone": "Europe/Madrid",
        "precision": "exact",
        "needs_review": False,
    }


def test_repeating_an_approval_creates_one_activity_and_keeps_legacy_fields():
    writer = Writer()
    first = register_meeting(
        proposal=_proposal(),
        decision="accept",
        operation_key="op-1",
        writer=writer,
        stage_mapping=None,
        existing=None,
    )
    second = register_meeting(
        proposal=_proposal(),
        decision="accept",
        operation_key="op-1",
        writer=writer,
        stage_mapping=None,
        existing=first,
    )
    assert writer.created == ["op-1"]
    assert writer.stages == []
    assert second["replayed"] is True
    assert second["remote_id"] == "act-1"
    assert second["stage_changed"] is False
    assert second["closes_deal"] is False
    payload = with_meeting({"note": "legacy"}, proposal_id="meet-1", input_revision="rev-3", decision="accept", starts_at=first["remote_id"] and "2026-09-29T15:00:00Z", timezone="Europe/Madrid")
    assert payload["note"] == "legacy"
    assert payload["meeting"]["decision"] == "accept"


def test_correcting_a_proposal_reuses_one_remote_activity():
    writer = Writer()
    accepted = register_meeting(
        proposal=_proposal(),
        decision="accept",
        operation_key="op-1",
        writer=writer,
        stage_mapping=None,
        existing=None,
    )
    corrected = register_meeting(
        proposal={**_proposal(), "starts_at": "2026-09-30T14:00:00+00:00"},
        decision="corrected",
        operation_key="op-1",
        writer=writer,
        stage_mapping=None,
        existing=accepted,
        starts_at="2026-09-30T14:00:00+00:00",
    )
    assert writer.created == ["op-1"]
    assert corrected["replayed"] is True
    assert corrected["remote_id"] == "act-1"


def test_a_timeout_is_reconciled_before_another_create_and_an_ambiguous_accept_is_refused():
    writer = Writer(fail_once=True)
    uncertain = register_meeting(
        proposal=_proposal(),
        decision="accept",
        operation_key="op-1",
        writer=writer,
        stage_mapping=None,
        existing=None,
    )
    assert uncertain["crm_status"] == "uncertain"
    assert writer.created == []
    recovered = register_meeting(
        proposal=_proposal(),
        decision="accept",
        operation_key="op-1",
        writer=writer,
        stage_mapping="stage-won",
        existing=uncertain,
    )
    assert recovered["remote_id"] == "act-1"
    assert recovered["replayed"] is True
    assert writer.created == []
    assert writer.stages == []
    ambiguous = {**_proposal(), "starts_at": None, "precision": "ambiguous", "needs_review": True}
    with pytest.raises(MeetingWriteError) as refused:
        register_meeting(
            proposal=ambiguous,
            decision="accept",
            operation_key="op-2",
            writer=writer,
            stage_mapping=None,
            existing=None,
        )
    assert refused.value.code == "needs_correction"


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


def test_two_workers_insert_one_meeting_write():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-meet-write-"))
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
        statement = insert_write_statement(
            operation_key="op-1", memo_id=MEMO, proposal_id="meet-1", remote_id="act-1", crm_status="succeeded",
        )
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
        counted = _psql(dsn, "SELECT count(*) FROM meeting_writes;")
        assert "1" in counted.stdout
        stage = _psql(dsn, "SELECT CASE WHEN stage_changed THEN 'changed' ELSE 'same' END FROM meeting_writes;")
        assert "same" in stage.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)
