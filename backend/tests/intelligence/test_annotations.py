"""F10 notes: one id is one note, and a stale revision does not erase the other edit."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-notes-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-notes-32")

import shutil
import socket
import subprocess
import tempfile
import threading
from pathlib import Path

import pytest

from app.services.intelligence.annotations import AnnotationError, accept_annotation, bind_capture, revise_statement

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "044_interaction_annotations_patterns.sql"
AUTHOR = "22222222-2222-2222-2222-222222222222"
COMPANY = "11111111-1111-1111-1111-111111111111"


def test_a_note_exists_before_the_memo_and_a_retry_is_the_same_note():
    store = {}
    first = accept_annotation(
        store,
        annotation_id="note-1",
        client_capture_id="cap-local-1",
        text="Lo dijo con ironía",
        offset_ms=134000,
        expected_revision=None,
        author_id="user-a",
        company_id="co-1",
    )
    assert first["memo_id"] is None
    assert first["source_type"] == "human_note"
    assert first["revision"] == 1
    again = accept_annotation(
        store,
        annotation_id="note-1",
        client_capture_id="cap-local-1",
        text="Lo dijo con ironía",
        offset_ms=1,
        expected_revision=1,
        author_id="user-a",
        company_id="co-1",
    )
    assert again["replayed"] is True
    assert again["offset_ms"] == 134000
    assert len(store) == 1
    bound = bind_capture(store, client_capture_id="cap-local-1", memo_id="memo-9", author_id="user-a")
    bind_capture(store, client_capture_id="cap-local-1", memo_id="memo-9", author_id="user-a")
    assert bound[0]["memo_id"] == "memo-9"
    assert len(store) == 1


def test_a_stale_revision_does_not_replace_the_text_and_another_author_cannot():
    store = {}
    accept_annotation(
        store,
        annotation_id="note-1",
        client_capture_id="cap-local-1",
        text="primera",
        offset_ms=10,
        expected_revision=None,
        author_id="user-a",
        company_id="co-1",
    )
    edited = accept_annotation(
        store,
        annotation_id="note-1",
        client_capture_id="cap-local-1",
        text="segunda",
        offset_ms=999,
        expected_revision=1,
        author_id="user-a",
        company_id="co-1",
    )
    assert edited["revision"] == 2
    assert edited["offset_ms"] == 10
    with pytest.raises(AnnotationError) as stale:
        accept_annotation(
            store,
            annotation_id="note-1",
            client_capture_id="cap-local-1",
            text="tercera",
            offset_ms=10,
            expected_revision=1,
            author_id="user-a",
            company_id="co-1",
        )
    assert stale.value.code == "conflict"
    assert store[("user-a", "note-1")]["text"] == "segunda"
    other = accept_annotation(
        store,
        annotation_id="note-1",
        client_capture_id="cap-local-1",
        text="ajena",
        offset_ms=10,
        expected_revision=None,
        author_id="user-b",
        company_id="co-1",
    )
    assert other["author_id"] == "user-b"
    assert store[("user-a", "note-1")]["text"] == "segunda"


def test_put_replay_is_the_same_note_and_a_stale_revision_conflicts():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import annotations as notes_api
    from app.deps import get_membership
    from app.services.company import Membership

    notes_api._NOTES.clear()
    app = FastAPI()
    app.include_router(notes_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active",
    )
    client = TestClient(app)
    body = {"text": "Lo dijo con ironía", "offset_ms": 134000}
    first = client.put("/api/v1/captures/cap-local-1/annotations/note-1", json=body)
    second = client.put("/api/v1/captures/cap-local-1/annotations/note-1", json={**body, "offset_ms": 1})
    assert first.status_code == 200
    assert second.json()["revision"] == 1
    assert second.json()["offset_ms"] == 134000
    assert second.json()["memo_id"] is None
    stale = client.put(
        "/api/v1/captures/cap-local-1/annotations/note-1",
        json={"text": "otra lectura", "offset_ms": 134000, "expected_revision": 0},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["text"] == "Lo dijo con ironía"


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


def test_two_revisions_of_the_same_note_leave_one_winner():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-notes-"))
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
        inserted = _psql(
            dsn,
            "INSERT INTO interaction_annotations "
            "(author_id, annotation_id, company_id, client_capture_id, text, offset_ms) VALUES "
            f"('{AUTHOR}', 'note-1', '{COMPANY}', 'cap-local-1', 'primera', 134000);",
        )
        assert inserted.returncode == 0, inserted.stderr
        outputs = []

        def write(text: str):
            outputs.append(_psql(dsn, revise_statement(
                author_id=AUTHOR, annotation_id="note-1", text=text, expected_revision=1,
            )).stdout)

        threads = [threading.Thread(target=write, args=(text,)) for text in ("segunda", "tercera")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sum(1 for output in outputs if "UPDATE 1" in output) == 1
        shown = _psql(dsn, "SELECT revision::text || ' ' || offset_ms::text FROM interaction_annotations;")
        assert "2 134000" in shown.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)
