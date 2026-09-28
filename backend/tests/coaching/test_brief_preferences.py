"""F11 preferences: highlighting later does not erase a ready brief or delay the job."""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-brief-pref-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-brief-pref-32")

import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.coaching.brief_preferences import (
    apply_preference,
    enqueue_brief,
    highlight_at,
    normalize_preference,
    publish_brief_statement,
    publish_if_newer,
    read_preference,
    set_supabase,
    write_preference,
)

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "047_post_interaction_briefs.sql"
MEMO = "77777777-7777-7777-7777-777777777777"
READY_AT = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)


def setup_function():
    from app.services.coaching import brief_preferences as mod

    mod._STORE.clear()
    set_supabase(None)


class _FakeSupabaseTable:
    def __init__(self, name: str, rows: dict[tuple, dict], upserts: list[dict]):
        self._name = name
        self._rows = rows
        self._upserts = upserts
        self._filters: dict[str, str] = {}

    def select(self, _columns: str):
        return self

    def eq(self, column: str, value: str):
        self._filters[column] = value
        return self

    def limit(self, _n: int):
        return self

    def upsert(self, payload: dict, on_conflict: str):
        self._upserts.append({"payload": payload, "on_conflict": on_conflict})
        key = (payload["user_id"],)
        self._rows[key] = dict(payload)
        return self

    def execute(self):
        if self._filters:
            uid = self._filters.get("user_id")
            row = self._rows.get((uid,)) if uid else None
            return SimpleNamespace(data=[row] if row else [])
        return SimpleNamespace(data=[])


class _FakeSupabase:
    def __init__(self):
        self.rows: dict[tuple, dict] = {}
        self.upserts: list[dict] = []

    def table(self, name: str):
        return _FakeSupabaseTable(name, self.rows, self.upserts)


def test_supabase_persists_preference_and_upserts_once():
    fake = _FakeSupabase()
    set_supabase(fake)
    user = "user-supabase-1"
    saved = write_preference(
        user,
        {"highlight_mode": "deferred", "delay_minutes": 30, "timezone": "America/New_York"},
    )
    assert saved == {
        "highlight_mode": "deferred",
        "delay_minutes": 30,
        "end_of_day": None,
        "timezone": "America/New_York",
    }
    assert read_preference(user) == saved
    write_preference(user, {"highlight_mode": "deferred", "delay_minutes": 45, "timezone": "America/New_York"})
    assert len(fake.upserts) == 2
    assert len(fake.rows) == 1
    assert read_preference(user)["delay_minutes"] == 45


def test_invalid_mode_still_raises_with_supabase():
    fake = _FakeSupabase()
    set_supabase(fake)
    with pytest.raises(ValueError, match="modo de destaque desconocido"):
        write_preference("user-bad", {"highlight_mode": "later_never"})
    assert fake.upserts == []


def test_supabase_read_failure_falls_back_to_memory():
    fake = _FakeSupabase()
    set_supabase(fake)
    user = "user-fallback"
    write_preference(user, {"highlight_mode": "immediate", "timezone": "Europe/Madrid"})
    table = MagicMock()
    table.select.return_value.eq.return_value.limit.return_value.execute.side_effect = RuntimeError("db down")
    broken = MagicMock()
    broken.table.return_value = table
    set_supabase(broken)
    assert read_preference(user) == {
        "highlight_mode": "immediate",
        "delay_minutes": None,
        "end_of_day": None,
        "timezone": "Europe/Madrid",
    }


def test_deferred_highlight_does_not_delay_brief_processing():
    jobs = enqueue_brief([], memo_id="memo-1", input_revision="rev-4")
    highlighted = apply_preference(
        {"status": "pending", "reason": "score_pending", "waiting": True, "sections": []},
        {"highlight_mode": "deferred", "timezone": "Europe/Madrid"},
    )
    assert jobs[0]["available_at"] == "now"
    assert highlighted["highlight"]["highlight_mode"] == "deferred"
    assert highlighted["waiting"] is True


def test_changing_the_preference_keeps_a_ready_brief():
    brief = {"status": "ready", "sections": [{"kind": "objections", "evidence_refs": ["ev-1"]}]}
    updated = apply_preference(brief, {"highlight_mode": "deferred", "timezone": "Europe/Madrid"})
    assert updated["status"] == "ready"
    assert updated["sections"] == brief["sections"]
    assert updated["highlight"]["delay_minutes"] == 30
    assert updated["highlight"]["highlight_mode"] == "deferred"
    shown = highlight_at(READY_AT, updated["highlight"])
    assert shown == datetime(2026, 9, 22, 16, 30, tzinfo=timezone.utc)
    jobs = enqueue_brief([], memo_id="memo-1", input_revision="rev-4")
    again = enqueue_brief(jobs, memo_id="memo-1", input_revision="rev-4")
    assert len(again) == 1
    assert again[0]["available_at"] == "now"


def test_a_late_older_brief_does_not_replace_the_current_one():
    current = {"revision_seq": 4, "status": "ready", "input_revision": "rev-4"}
    late = {"revision_seq": 3, "status": "ready", "input_revision": "rev-3"}
    assert publish_if_newer(current, late) is None
    assert publish_if_newer(None, late) == late
    early = datetime(2026, 9, 22, 15, 0, tzinfo=timezone.utc)
    end = highlight_at(early, normalize_preference({"highlight_mode": "end_of_day", "timezone": "Europe/Madrid"}))
    local = end.astimezone(ZoneInfo("Europe/Madrid"))
    assert local.hour == 18
    assert local.day == 22


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


def test_postgres_keeps_the_newer_brief_when_an_older_one_finishes_late():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-brief-"))
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
        newer = publish_brief_statement(
            memo_id=MEMO, input_revision="rev-4", revision_seq=4, status="ready", body={"mark": "current"},
        )
        older = publish_brief_statement(
            memo_id=MEMO, input_revision="rev-4", revision_seq=3, status="pending", body={"mark": "late"},
        )
        assert _psql(dsn, newer).returncode == 0
        assert _psql(dsn, older).returncode == 0
        shown = _psql(dsn, "SELECT body->>'mark' FROM post_interaction_briefs;")
        assert "current" in shown.stdout
        assert "late" not in shown.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)
