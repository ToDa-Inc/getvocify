"""F09 score: no playbook and a fake citation publish no mark. A won deal is not a bonus."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-scoring-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-scoring-32b")

import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.services.coaching.scoring import assemble_score, publish_score_statement

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "045_memo_scores.sql"
MEMO = "55555555-5555-5555-5555-555555555555"
PLAYBOOK = {"id": "pb-1", "ambiguous": False}
AMBIGUOUS = {"id": "pb-1", "ambiguous": True}


def _score(**overrides):
    base = dict(
        playbook=PLAYBOOK,
        criteria_statuses=["met", "missed", "unknown", "not_applicable"],
        evidence_refs=["ev-1"],
        cited_refs=["ev-1"],
        proposed_value=6,
        crm_outcome=None,
        input_revision="rev-2",
        playbook_version_id="pv-2",
    )
    base.update(overrides)
    return assemble_score(**base)


def test_a_missing_or_ambiguous_playbook_has_no_mark():
    missing = _score(playbook=None)
    assert missing["value"] is None
    assert missing["reason"] == "missing_playbook"
    assert missing["status"] == "unavailable"
    ambiguous = _score(playbook=AMBIGUOUS)
    assert ambiguous["value"] is None
    assert ambiguous["reason"] == "ambiguous_playbook"
    assert ambiguous["status"] == "partial"
    assert ambiguous["adherence"] == 0.5
    assert ambiguous["met_steps"] == 1
    assert ambiguous["unknown_steps"] == 1


def test_the_same_evidence_keeps_the_mark_when_the_deal_outcome_changes():
    won = _score(crm_outcome="closed_won")
    lost = _score(crm_outcome="closed_lost")
    assert won["value"] == lost["value"] == 6
    assert won["adherence"] == lost["adherence"]
    assert won["crm_outcome"] == "closed_won"
    assert lost["crm_outcome"] == "closed_lost"


def test_a_citation_that_is_not_in_the_evidence_is_not_published():
    rejected = _score(cited_refs=["ev-missing"])
    assert rejected["status"] == "failed"
    assert rejected["value"] is None
    assert rejected["reason"] == "uncited_evidence"


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


def test_an_older_revision_does_not_replace_the_stored_mark():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-score-"))
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
        current = _score()
        older = _score(proposed_value=1)
        assert _psql(dsn, publish_score_statement(
            memo_id=MEMO, input_revision="rev-2", revision_seq=2, score=current,
        )).returncode == 0
        stale = _psql(dsn, publish_score_statement(
            memo_id=MEMO, input_revision="rev-2", revision_seq=1, score=older,
        ))
        assert stale.returncode == 0, stale.stderr
        shown = _psql(dsn, "SELECT 'mark-' || (score->>'value') FROM memo_scores;")
        assert "mark-6" in shown.stdout
        assert "mark-1" not in shown.stdout
        counted = _psql(dsn, "SELECT count(*) FROM memo_scores;")
        assert "1" in counted.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)
