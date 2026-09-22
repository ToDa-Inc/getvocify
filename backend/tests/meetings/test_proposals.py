"""F14: a tentative meeting is not agreed, and five o'clock is not 17:00."""

import os
from datetime import datetime

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-meetings-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-meetings-32")

import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.services.meetings.proposals import build_proposal, insert_proposal_statement
from app.services.meetings.time_resolution import local_time_is_ambiguous

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "046_meeting_proposals.sql"
MEMO = "66666666-6666-6666-6666-666666666666"


def test_we_could_meet_is_not_a_confirmed_agreement():
    proposal = build_proposal(
        proposal_id="meet-1",
        phrase="Podríamos vernos",
        tz_name="Europe/Madrid",
        evidence_refs=["ev-5"],
        uploaded_at="2026-09-22T09:00:00+00:00",
    )
    assert proposal["agreement"] == "unknown"
    assert proposal["agreement"] != "agreed"
    assert proposal["starts_at"] is None
    assert proposal["starts_at"] != "2026-09-22T09:00:00+00:00"
    assert proposal["crm_status"] == "not_requested"
    assert proposal["closes_deal"] is False


def test_a_corrected_time_keeps_the_last_time_both_confirmed():
    proposal = build_proposal(
        proposal_id="meet-1",
        phrase="quedamos a las 16:00",
        tz_name="Europe/Madrid",
        evidence_refs=["ev-1"],
        corrections=[{
            "starts_at": "2026-09-29T15:00:00+00:00",
            "evidence_ref": "ev-correction",
            "confirmed_by_both": True,
        }],
    )
    assert proposal["agreement"] == "agreed"
    assert proposal["starts_at"] == "2026-09-29T15:00:00+00:00"
    assert proposal["precision"] == "exact"
    assert "ev-correction" in proposal["evidence_refs"]
    assert proposal["closes_deal"] is False


def test_five_oclock_without_context_is_not_seventeen():
    proposal = build_proposal(
        proposal_id="meet-1",
        phrase="a las cinco",
        tz_name="Europe/Madrid",
        evidence_refs=["ev-5"],
    )
    assert proposal["precision"] == "ambiguous"
    assert proposal["starts_at"] is None
    assert proposal["needs_review"] is True


def test_a_repeated_dst_hour_asks_for_review():
    assert local_time_is_ambiguous(2026, 10, 25, 2, 30, "Europe/Madrid") is True
    proposal = build_proposal(
        proposal_id="meet-1",
        phrase="a las 02:30",
        tz_name="Europe/Madrid",
        evidence_refs=["ev-5"],
        on=datetime(2026, 10, 25, 2, 30),
    )
    assert proposal["starts_at"] is None
    assert proposal["precision"] == "ambiguous"
    assert proposal["needs_review"] is True


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


def test_an_ambiguous_proposal_is_stored_without_a_start_time():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-meet-"))
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
        proposal = build_proposal(
            proposal_id="meet-1",
            phrase="a las cinco",
            tz_name="Europe/Madrid",
            evidence_refs=["ev-5"],
        )
        saved = _psql(dsn, insert_proposal_statement(MEMO, "rev-1", proposal))
        assert saved.returncode == 0, saved.stderr
        shown = _psql(dsn, "SELECT CASE WHEN starts_at IS NULL THEN 'empty' ELSE 'filled' END FROM meeting_proposals;")
        assert "empty" in shown.stdout
        assert "filled" not in shown.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)
