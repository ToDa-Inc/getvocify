"""F10 patterns: an obstacle is not a lost sale, and a new revision does not double the count."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-patterns-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-patterns-32")

import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.services.intelligence.patterns import (
    CATEGORIES,
    apply_projection,
    attribute_evidence,
    frequency,
    objection_view,
    pattern_from_situation,
    patterns_from_extraction,
    project_patterns,
    supersede_statement,
)

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "044_interaction_annotations_patterns.sql"
MEMO = "44444444-4444-4444-4444-444444444444"


def test_an_extraction_projects_objections_and_a_later_one_replaces_them():
    first = project_patterns(
        [{"pattern_id": "human-1", "memo_id": "memo-1", "input_revision": "rev-0", "superseded": False}],
        memo_id="memo-1",
        input_revision="rev-1",
        extraction={"objections": ["Está caro", {"text": "Falta parking", "commercial_objection": False}]},
    )
    owned = [row for row in first if str(row["pattern_id"]).startswith("objection:")]
    assert frequency(owned) == 2
    assert next(row for row in owned if row["pattern_id"] == "objection:está caro")["kind"] == "objection"
    assert next(row for row in owned if "parking" in row["pattern_id"])["kind"] == "obstacle"
    assert next(row for row in first if row["pattern_id"] == "human-1")["superseded"] is False

    second = project_patterns(first, memo_id="memo-1", input_revision="rev-2", extraction={"objections": []})
    assert frequency([row for row in second if str(row["pattern_id"]).startswith("objection:")]) == 0
    assert next(row for row in second if row["pattern_id"] == "human-1")["superseded"] is False
    pattern = pattern_from_situation(
        pattern_id="pat-drive",
        memo_id="memo-1",
        input_revision="rev-1",
        category="other",
        commercial_objection=False,
        resolution="unknown",
    )
    assert pattern["kind"] == "obstacle"
    assert pattern["kind"] != "objection"
    assert pattern["resolution"] == "unknown"
    assert pattern["response"] is None


def test_an_irony_note_is_evidence_and_not_the_prospects_words():
    attributed = attribute_evidence(
        transcript_quotes=[{
            "id": "ev-1",
            "source_id": "turn-1",
            "source_type": "transcript",
            "quote": "qué barato",
        }],
        note={"id": "note-1", "text": "Lo dijo con ironía"},
        sources={"turn-1": "qué barato, qué barato", "note-1": "Lo dijo con ironía"},
    )
    assert attributed["evidence_refs"] == ["ev-1", "note-1"]
    assert "Lo dijo con ironía" not in attributed["prospect_quotes"]
    assert attributed["prospect_quotes"] == ["qué barato"]


def test_categories_stay_on_the_agreed_taxonomy():
    assert CATEGORIES == {"price", "timing", "authority", "competitor", "status_quo", "trust", "other"}
    row = pattern_from_situation(
        pattern_id="pat-x",
        memo_id="memo-1",
        input_revision="rev-1",
        category="not_in_taxonomy",
        commercial_objection=True,
        resolution="unknown",
    )
    assert row["category"] == "other"


def test_driving_now_is_an_obstacle_not_a_commercial_objection():
    rows = patterns_from_extraction(
        memo_id="memo-1",
        input_revision="rev-1",
        extraction={"objections": [{"text": "Ahora estoy conduciendo", "commercial_objection": False}]},
    )
    assert len(rows) == 1
    assert rows[0]["kind"] == "obstacle"
    assert rows[0]["kind"] != "objection"


def test_review_keeps_one_interaction_scope_without_team_rollup():
    view = objection_view(
        notes=[{"annotation_id": "note-1", "text": "matiz", "offset_ms": 1000, "author_id": "user-a", "turn_id": None}],
        patterns=[
            {
                "pattern_id": "pat-1",
                "category": "price",
                "kind": "objection",
                "resolution": "open",
                "response": "Comparar plazos",
                "prospect_quotes": ["está caro"],
                "superseded": False,
            },
            {
                "pattern_id": "pat-old",
                "category": "price",
                "kind": "objection",
                "resolution": "unknown",
                "response": None,
                "prospect_quotes": [],
                "superseded": True,
            },
        ],
        readable=True,
    )
    assert view["coverage"] == "complete"
    assert len(view["patterns"]) == 1
    assert view["patterns"][0]["pattern_id"] == "pat-1"
    assert "count" not in view


def test_a_corrected_resolution_replaces_the_previous_frequency():
    first = pattern_from_situation(
        pattern_id="pat-1",
        memo_id="memo-1",
        input_revision="rev-1",
        category="price",
        commercial_objection=True,
        resolution="open",
        evidence_refs=["ev-1"],
    )
    second = pattern_from_situation(
        pattern_id="pat-1",
        memo_id="memo-1",
        input_revision="rev-2",
        category="price",
        commercial_objection=True,
        resolution="resolved",
        evidence_refs=["ev-1", "note-1"],
    )
    projected = apply_projection([first], [second])
    assert frequency(projected) == 1
    current = [row for row in projected if not row["superseded"]]
    assert current[0]["input_revision"] == "rev-2"
    assert current[0]["resolution"] == "resolved"
    assert len(projected) == 2


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


def test_postgres_keeps_both_revisions_and_one_current_frequency():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-patterns-"))
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
        for revision, resolution in (("rev-1", "open"), ("rev-2", "resolved")):
            inserted = _psql(
                dsn,
                "INSERT INTO interaction_patterns "
                "(memo_id, pattern_id, input_revision, category, kind, resolution, evidence_refs) VALUES "
                f"('{MEMO}', 'pat-1', '{revision}', 'price', 'objection', '{resolution}', '[\"ev-1\"]'::jsonb);",
            )
            assert inserted.returncode == 0, inserted.stderr
        marked = _psql(dsn, supersede_statement(memo_id=MEMO, pattern_id="pat-1", input_revision="rev-2"))
        assert marked.returncode == 0, marked.stderr
        counted = _psql(dsn, "SELECT count(*) FROM interaction_patterns;")
        current = _psql(dsn, "SELECT count(*) FROM interaction_patterns WHERE superseded = FALSE;")
        assert "2" in counted.stdout
        assert "1" in current.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)
