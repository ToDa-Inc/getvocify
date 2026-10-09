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

from app.services.meetings.proposals import (
    build_proposal,
    infer_agreement,
    insert_proposal_statement,
    latest_proposal,
    proposal_from_meeting,
)
from app.services.meetings.time_resolution import local_time_is_ambiguous, resolve_phrase

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "046_meeting_proposals.sql"
MEMO = "66666666-6666-6666-6666-666666666666"


def test_the_newest_proposal_is_the_one_on_the_memo_and_none_is_empty():
    assert latest_proposal([]) is None
    chosen = latest_proposal([
        {"proposal_id": "old", "agreement": "agreed", "starts_at": "2026-09-22T15:00:00Z", "created_at": "2026-09-22T09:00:00Z", "decision": "pending", "crm_status": "not_requested", "timezone": "Europe/Madrid"},
        {"proposal_id": "new", "agreement": "unknown", "starts_at": None, "created_at": "2026-09-22T11:00:00Z", "decision": "pending", "crm_status": "not_requested"},
    ])
    assert chosen["proposal_id"] == "new"
    assert chosen["needs_review"] is True
    agreed = latest_proposal([
        {"proposal_id": "yes", "agreement": "agreed", "starts_at": "2026-09-29T15:00:00Z", "created_at": "2026-09-22T12:00:00Z", "timezone": "Europe/Madrid"},
    ])
    assert agreed["needs_review"] is False
    assert agreed["starts_at"] == "2026-09-29T15:00:00Z"


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


def test_a_date_without_hour_does_not_default_to_nine():
    resolved = resolve_phrase("quedamos el martes", tz_name="Europe/Madrid")
    assert resolved["precision"] == "date_only"
    assert resolved["starts_at"] is None
    proposal = build_proposal(
        proposal_id="meet-1",
        phrase="quedamos el martes",
        tz_name="Europe/Madrid",
        evidence_refs=["ev-2"],
    )
    assert proposal["starts_at"] is None
    assert "09:00" not in str(proposal.get("starts_at") or "")


def test_reopening_review_keeps_the_same_proposal_and_decision():
    stored = {
        "proposal_id": "meet-1",
        "agreement": "agreed",
        "starts_at": "2026-09-29T15:00:00+00:00",
        "created_at": "2026-09-22T12:00:00Z",
        "timezone": "Europe/Madrid",
        "decision": "accepted",
        "crm_status": "succeeded",
    }
    first = latest_proposal([stored])
    second = latest_proposal([stored])
    assert first == second
    assert first["decision"] == "accepted"
    assert first["crm_status"] == "succeeded"


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


def _meeting(**overrides):
    base = {
        "agreed": True,
        "starts_at": "2026-10-01T10:00:00+02:00",
        "timezone": None,
        "precision": "time",
        "evidence_refs": ["ev-accept"],
    }
    base.update(overrides)
    return base


def test_an_exact_time_both_accepted_is_a_booked_meeting():
    proposal = proposal_from_meeting(proposal_id="meet-1", meeting=_meeting(), tz_name="Europe/Madrid")
    assert proposal["agreement"] == "agreed"
    assert proposal["starts_at"] == "2026-10-01T10:00:00+02:00"
    assert proposal["precision"] == "exact"
    assert proposal["needs_review"] is False
    assert proposal["evidence_refs"] == ["ev-accept"]
    assert proposal["closes_deal"] is False


def test_an_agreed_day_without_time_waits_for_review_without_inventing_an_hour():
    proposal = proposal_from_meeting(
        proposal_id="meet-1",
        meeting=_meeting(starts_at="2026-10-01", precision="date"),
        tz_name="Europe/Madrid",
    )
    assert proposal["agreement"] == "agreed"
    assert proposal["starts_at"] is None
    assert proposal["precision"] == "date_only"
    assert proposal["needs_review"] is True


def test_an_offset_that_is_not_the_memo_zone_is_ambiguous():
    proposal = proposal_from_meeting(
        proposal_id="meet-1",
        meeting=_meeting(starts_at="2026-10-01T10:00:00+01:00"),
        tz_name="Europe/Madrid",
    )
    assert proposal["starts_at"] is None
    assert proposal["precision"] == "ambiguous"
    assert proposal["needs_review"] is True


def test_a_repeated_dst_hour_from_intelligence_is_ambiguous():
    proposal = proposal_from_meeting(
        proposal_id="meet-1",
        meeting=_meeting(starts_at="2026-10-25T02:30:00+02:00"),
        tz_name="Europe/Madrid",
    )
    assert proposal["starts_at"] is None
    assert proposal["precision"] == "ambiguous"


def test_no_agreement_or_a_refusal_is_not_a_proposal():
    assert proposal_from_meeting(proposal_id="m", meeting=_meeting(agreed=None, starts_at=None, precision="unknown"), tz_name="Europe/Madrid") is None
    assert proposal_from_meeting(proposal_id="m", meeting=_meeting(agreed=False, starts_at=None, precision="unknown"), tz_name="Europe/Madrid") is None
    assert proposal_from_meeting(proposal_id="m", meeting={}, tz_name="Europe/Madrid") is None


def test_an_invitation_the_rep_sends_counts_as_agreement_in_the_fallback():
    assert infer_agreement("Vale, te pongo una reunión y te mando la invitación") == "agreed"
    assert infer_agreement("Podríamos vernos, te mando la invitación si eso") == "unknown"


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
