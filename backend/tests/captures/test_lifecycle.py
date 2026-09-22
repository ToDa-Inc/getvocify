"""F01.02 — identidad de captura idempotente y ámbito por sesión."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.captures import router as captures_router
from app.deps import get_membership, get_supabase, get_user_id
from app.services.captures import (
    CAPTURE_STATUS_TO_MEMO_STATUS,
    CaptureContentConflict,
    MEMO_PIPELINE_STATUSES,
    complete_capture,
    insert_memo_row,
    reserve_capture,
)
from app.services.company import Membership

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"
COMPANY_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COMPANY_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CLIENT_CAPTURE = "cap-local-1"
STARTED_AT = "2026-09-22T08:00:00Z"
MIGRATION = (
    Path(__file__).resolve().parents[2] / "migrations" / "037_memo_capture_context.sql"
)


class DuplicateKey(Exception):
    def __str__(self) -> str:
        return (
            'duplicate key value violates unique constraint '
            '"idx_memos_user_client_capture_id_unique" (23505)'
        )


class FakeQuery:
    def __init__(self, store: list[dict]):
        self.store = store
        self._filters: list[tuple[str, object]] = []
        self._op = "select"
        self._payload: dict | None = None
        self._limit: int | None = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = dict(row)
        return self

    def update(self, row):
        self._op = "update"
        self._payload = dict(row)
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, n, *_a, **_k):
        self._limit = n
        return self

    def _match(self, row: dict) -> bool:
        return all(row.get(column) == value for column, value in self._filters)

    def execute(self):
        if self._op == "insert":
            row = dict(self._payload or {})
            row.setdefault("id", str(uuid.uuid4()))
            key = (row.get("user_id"), row.get("client_capture_id"))
            if row.get("client_capture_id"):
                for existing in self.store:
                    if (existing.get("user_id"), existing.get("client_capture_id")) == key:
                        raise DuplicateKey()
            self.store.append(row)
            return SimpleNamespace(data=[dict(row)])
        rows = [dict(r) for r in self.store if self._match(r)]
        if self._op == "update":
            for row in self.store:
                if self._match(row):
                    row.update(self._payload or {})
            rows = [dict(r) for r in self.store if self._match(r)]
        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows)


def fake_db(rows: list[dict] | None = None):
    store = list(rows or [])

    def table(name: str):
        assert name == "memos"
        return FakeQuery(store)

    client = MagicMock()
    client.table.side_effect = table
    return client, store


def _membership(user_id: str, company_id: str) -> Membership:
    return Membership(
        id=f"mem-{user_id[:8]}",
        company_id=company_id,
        user_id=user_id,
        role="member",
        status="active",
    )


def _client(supabase, *, user_id: str, company_id: str) -> TestClient:
    app = FastAPI()
    app.include_router(captures_router)
    app.dependency_overrides[get_supabase] = lambda: supabase
    app.dependency_overrides[get_user_id] = lambda: user_id
    app.dependency_overrides[get_membership] = lambda: _membership(user_id, company_id)
    return TestClient(app)


def test_capture_statuses_map_onto_existing_memo_enum():
    assert set(CAPTURE_STATUS_TO_MEMO_STATUS) == {
        "recording",
        "upload_pending",
        "processing",
        "complete",
        "failed",
    }
    for memo_status in CAPTURE_STATUS_TO_MEMO_STATUS.values():
        assert memo_status in MEMO_PIPELINE_STATUSES
    assert "recording" not in MEMO_PIPELINE_STATUSES
    assert "upload_pending" not in MEMO_PIPELINE_STATUSES


def test_insert_memo_row_always_persists_source_type():
    supabase, store = fake_db()
    row = insert_memo_row(
        supabase,
        {
            "user_id": USER_A,
            "audio_url": "",
            "audio_duration": 12.0,
            "status": "extracting",
            "transcript": "hola",
            "source_type": "meeting_transcript",
        },
    )
    assert row["source_type"] == "meeting_transcript"
    assert store[0]["source_type"] == "meeting_transcript"


def test_create_capture_returns_reserved_memo_identity():
    supabase, store = fake_db()
    client = _client(supabase, user_id=USER_A, company_id=COMPANY_A)
    res = client.post(
        "/api/v1/captures",
        json={
            "client_capture_id": CLIENT_CAPTURE,
            "started_at": STARTED_AT,
            "interaction_kind": "meeting",
            "company_id": COMPANY_B,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["capture_id"] == body["memo_id"]
    assert body["status"] == "recording"
    assert store[0]["user_id"] == USER_A
    assert store[0]["company_id"] == COMPANY_A
    assert store[0]["client_capture_id"] == CLIENT_CAPTURE
    assert store[0]["interaction_kind"] == "meeting"
    assert store[0]["source_type"] == "meeting_transcript"
    assert store[0]["status"] == "uploading"


def test_repeat_post_same_author_returns_same_ids():
    supabase, _store = fake_db()
    first = reserve_capture(
        supabase,
        user_id=USER_A,
        company_id=COMPANY_A,
        client_capture_id=CLIENT_CAPTURE,
        started_at=STARTED_AT,
        interaction_kind="meeting",
    )
    second = reserve_capture(
        supabase,
        user_id=USER_A,
        company_id=COMPANY_A,
        client_capture_id=CLIENT_CAPTURE,
        started_at=STARTED_AT,
        interaction_kind="meeting",
    )
    assert first.capture_id == second.capture_id == first.memo_id == second.memo_id
    assert first.status == second.status == "recording"


def test_same_client_capture_id_other_author_does_not_return_foreign_memo():
    supabase, store = fake_db()
    owned = reserve_capture(
        supabase,
        user_id=USER_A,
        company_id=COMPANY_A,
        client_capture_id=CLIENT_CAPTURE,
        started_at=STARTED_AT,
        interaction_kind="meeting",
    )
    other = reserve_capture(
        supabase,
        user_id=USER_B,
        company_id=COMPANY_B,
        client_capture_id=CLIENT_CAPTURE,
        started_at=STARTED_AT,
        interaction_kind="meeting",
    )
    assert owned.capture_id != other.capture_id
    assert {row["user_id"] for row in store} == {USER_A, USER_B}
    with pytest.raises(HTTPException) as exc:
        complete_capture(
            supabase,
            user_id=USER_B,
            company_id=COMPANY_B,
            capture_id=owned.capture_id,
            transcript="hola",
            audio_duration=8.0,
        )
    assert exc.value.status_code == 404


def test_complete_same_content_is_idempotent():
    supabase, store = fake_db()
    reserved = reserve_capture(
        supabase,
        user_id=USER_A,
        company_id=COMPANY_A,
        client_capture_id=CLIENT_CAPTURE,
        started_at=STARTED_AT,
        interaction_kind="meeting",
    )
    payload = {"transcript": "Quedamos el martes", "audio_duration": 42.0}
    first = complete_capture(
        supabase,
        user_id=USER_A,
        company_id=COMPANY_A,
        capture_id=reserved.capture_id,
        **payload,
    )
    store[0]["extraction"] = {"summary": "primera extracción"}
    second = complete_capture(
        supabase,
        user_id=USER_A,
        company_id=COMPANY_A,
        capture_id=reserved.capture_id,
        **payload,
    )
    assert first.capture_id == second.capture_id == reserved.capture_id
    assert first.memo_id == second.memo_id
    assert store[0]["extraction"] == {"summary": "primera extracción"}
    assert first.should_start_pipeline is True
    assert second.should_start_pipeline is False


def test_complete_incompatible_content_does_not_overwrite_extraction():
    supabase, store = fake_db()
    reserved = reserve_capture(
        supabase,
        user_id=USER_A,
        company_id=COMPANY_A,
        client_capture_id=CLIENT_CAPTURE,
        started_at=STARTED_AT,
        interaction_kind="meeting",
    )
    store[0]["extraction"] = {"summary": "vigente"}
    complete_capture(
        supabase,
        user_id=USER_A,
        company_id=COMPANY_A,
        capture_id=reserved.capture_id,
        transcript="versión A",
        audio_duration=10.0,
    )
    with pytest.raises(CaptureContentConflict) as exc:
        complete_capture(
            supabase,
            user_id=USER_A,
            company_id=COMPANY_A,
            capture_id=reserved.capture_id,
            transcript="versión B incompatible",
            audio_duration=10.0,
        )
    assert store[0]["extraction"] == {"summary": "vigente"}
    assert store[0]["transcript"] == "versión A"
    assert exc.value.needs_new_review is True
    assert exc.value.capture_id == reserved.capture_id


def _production_looking_dsn(url: str) -> bool:
    lowered = url.lower()
    return "supabase.co" in lowered or "railway.app" in lowered or "getvocify.com" in lowered


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


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


def _start_isolated_postgres() -> tuple[str, subprocess.Popen[bytes] | None, Path | None]:
    env_url = (os.environ.get("VOCIFY_TEST_DATABASE_URL") or "").strip()
    if env_url:
        if _production_looking_dsn(env_url):
            pytest.skip("VOCIFY_TEST_DATABASE_URL parece producción; no se usa")
        return env_url, None, None

    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres:
        pytest.skip("No hay PostgreSQL aislado; no se finge el lock en memoria")

    datadir = Path(tempfile.mkdtemp(prefix="vocify-capture-pg-"))
    port = _free_port()
    init = subprocess.run(
        [
            initdb,
            "-D",
            str(datadir),
            "--auth=trust",
            "--no-instructions",
            "-U",
            "vocify",
            "--encoding=UTF8",
            "--locale=C",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_pg_env(),
    )
    if init.returncode != 0:
        shutil.rmtree(datadir, ignore_errors=True)
        pytest.skip(f"initdb falló: {init.stderr[-400:]}")

    log_path = datadir / "pg.log"
    proc = subprocess.Popen(
        [
            postgres,
            "-D",
            str(datadir),
            "-p",
            str(port),
            "-h",
            "127.0.0.1",
            "-k",
            str(datadir),
        ],
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
        env=_pg_env(),
    )
    dsn = f"postgresql://vocify@127.0.0.1:{port}/postgres"
    for _ in range(40):
        if proc.poll() is not None:
            log = log_path.read_text() if log_path.exists() else ""
            shutil.rmtree(datadir, ignore_errors=True)
            pytest.skip(f"postgres aislado salió: {log[-400:]}")
        ping = _psql(dsn, "SELECT 1;")
        if ping.returncode == 0:
            return dsn, proc, datadir
        time.sleep(0.15)
    proc.terminate()
    shutil.rmtree(datadir, ignore_errors=True)
    pytest.skip("PostgreSQL aislado no respondió a tiempo")


def _stop_isolated_postgres(proc: subprocess.Popen[bytes] | None, datadir: Path | None) -> None:
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    if datadir is not None:
        shutil.rmtree(datadir, ignore_errors=True)


def test_concurrent_inserts_same_author_client_capture_id_create_one_memo():
    dsn, proc, datadir = _start_isolated_postgres()
    try:
        bootstrap = _psql(
            dsn,
            """
            CREATE SCHEMA IF NOT EXISTS auth;
            CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
              LANGUAGE sql AS $$ SELECT NULL::uuid $$;
            CREATE TABLE companies (id UUID PRIMARY KEY);
            CREATE TABLE company_members (
              company_id UUID,
              user_id UUID,
              status TEXT
            );
            CREATE TABLE memos (
              id UUID PRIMARY KEY,
              user_id UUID NOT NULL,
              status TEXT NOT NULL DEFAULT 'uploading',
              source TEXT DEFAULT 'web'
            );
            """,
        )
        assert bootstrap.returncode == 0, bootstrap.stderr
        assert MIGRATION.is_file(), "falta 037_memo_capture_context.sql"
        applied = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(MIGRATION)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=_pg_env(),
        )
        assert applied.returncode == 0, applied.stderr

        user_id = USER_A
        cap = CLIENT_CAPTURE
        errors: list[str] = []
        barrier = threading.Barrier(2)

        def insert_one(memo_id: str) -> None:
            barrier.wait(timeout=5)
            result = _psql(
                dsn,
                f"""
                BEGIN;
                INSERT INTO memos (id, user_id, client_capture_id, status, capture_status)
                VALUES ('{memo_id}', '{user_id}', '{cap}', 'uploading', 'recording');
                SELECT pg_sleep(0.35);
                COMMIT;
                """,
                timeout=15,
            )
            if result.returncode != 0:
                errors.append(result.stderr)

        t1 = threading.Thread(
            target=insert_one, args=("aaaaaaaa-aaaa-aaaa-aaaa-000000000001",)
        )
        t2 = threading.Thread(
            target=insert_one, args=("aaaaaaaa-aaaa-aaaa-aaaa-000000000002",)
        )
        t1.start()
        t2.start()
        t1.join(timeout=20)
        t2.join(timeout=20)

        count = _psql(
            dsn,
            f"SELECT count(*) FROM memos WHERE user_id = '{user_id}' "
            f"AND client_capture_id = '{cap}';",
        )
        assert count.returncode == 0, count.stderr
        assert count.stdout.strip().splitlines()[-2].strip() == "1"
        assert any("duplicate key" in err.lower() or "unique" in err.lower() for err in errors)
    finally:
        _stop_isolated_postgres(proc, datadir)
