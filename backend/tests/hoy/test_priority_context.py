"""F04 context: an unfinished CRM page is not 'never called', and two connections stay two people."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-context-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-context-32")

import shutil
import socket
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.hoy.assigned import collect_assigned, parse_assigned_page
from app.services.hoy.context import (
    build_priority_page,
    fold_context,
    invalidate_context,
    snapshot_from_rows,
    upsert_statements,
)
from app.services.hoy.priority import rank_candidates

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "042_contact_priority_context.sql"
COMPANY = "11111111-1111-1111-1111-111111111111"
ANA = "22222222-2222-2222-2222-222222222222"
LUIS = "33333333-3333-3333-3333-333333333333"
NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
MEMBERS = [
    {"user_id": ANA, "email": "ana@vocify.test", "name": "Ana Lopez"},
    {"user_id": LUIS, "email": "luis@vocify.test", "name": "Luis"},
]


def _page(provider: str, payload: dict, connection_id: str, observed_at: str = "2026-09-22T09:00:00Z") -> dict:
    return parse_assigned_page(provider, payload, connection_id=connection_id, observed_at=observed_at)


def test_an_unfinished_page_from_either_crm_is_not_never_called():
    hubspot = _page("hubspot", {
        "results": [{"id": "42", "properties": {"owner_email": "ana@vocify.test"}}],
        "paging": {"next": {"after": "100"}},
    }, "crm-A")
    pipedrive = _page("pipedrive", {
        "data": [{"id": 7, "owner_id": {"email": "ana@vocify.test", "name": "Ana Lopez"}}],
        "additional_data": {"pagination": {"more_items_in_collection": True, "next_start": 100}},
    }, "crm-B")
    rows = fold_context(company_id=COMPANY, pages=[hubspot, pipedrive], members=MEMBERS)
    assert {row["connection_id"] for row in rows} == {"crm-A", "crm-B"}
    assert all(row["history_complete"] is False for row in rows)
    ranked = rank_candidates(snapshot_from_rows(rows, connected=True)["candidates"], NOW)
    assert [row["never_called"] for row in ranked] == [False, False]
    assert {row["id"] for row in ranked} == {"crm-A:42:", "crm-B:7:"}


def test_an_ambiguous_email_stays_out_and_a_shared_name_does_not_assign():
    ambiguous = _page("hubspot", {
        "results": [{"id": "42", "properties": {"owner_email": "sam@vocify.test", "owner_name": "Ana Lopez"}}],
    }, "crm-A")
    named = _page("pipedrive", {
        "data": [{"id": 9, "owner_id": {"email": "other@example.com", "name": "Ana Lopez"}}],
    }, "crm-B")
    duplicated = [*MEMBERS, {"user_id": LUIS, "email": "sam@vocify.test", "name": "Sam"}]
    duplicated.append({"user_id": ANA, "email": "sam@vocify.test", "name": "Ana Lopez"})
    rows = fold_context(company_id=COMPANY, pages=[ambiguous, named], members=duplicated)
    by_connection = {row["connection_id"]: row for row in rows}
    assert by_connection["crm-A"]["owner_ambiguous"] is True
    assert by_connection["crm-A"]["owner_user_id"] is None
    assert by_connection["crm-B"]["owner_user_id"] is None
    assert by_connection["crm-B"]["owner_ambiguous"] is False
    page = build_priority_page(
        snapshot=snapshot_from_rows([by_connection["crm-A"]], connected=True),
        user_id=ANA,
        role="member",
        now=NOW,
    )
    assert page["items"] == []


def test_a_failed_refresh_keeps_the_previous_time():
    first = fold_context(
        company_id=COMPANY,
        pages=[_page("hubspot", {"results": [{"id": "42", "properties": {"owner_email": "ana@vocify.test", "last_call_at": None}}]}, "crm-A")],
        members=MEMBERS,
    )
    failed = _page("hubspot", {"error_kind": "timeout"}, "crm-A", observed_at="2026-09-22T12:00:00Z")
    kept = fold_context(company_id=COMPANY, pages=[failed], members=MEMBERS, previous=first)
    assert kept[0]["observed_at"] == "2026-09-22T09:00:00Z"
    assert kept[0]["coverage"] == "unavailable"
    assert kept[0]["history_complete"] is False
    stale = invalidate_context(first, "nueva interacción")
    assert stale[0]["observed_at"] == "2026-09-22T09:00:00Z"
    assert stale[0]["payload"]["stale_reason"] == "nueva interacción"
    assert stale[0]["coverage"] == "partial"


def _pg_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def _psql(dsn: str, sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        env=_pg_env(),
    )


def _start_postgres():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-priority-pg-"))
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
            pytest.skip((log_path.read_text() if log_path.exists() else "")[-300:])
        if _psql(dsn, "SELECT 1;").returncode == 0:
            return dsn, proc, datadir
        import time
        time.sleep(0.15)
    proc.terminate()
    shutil.rmtree(datadir, ignore_errors=True)
    pytest.skip("postgres no respondió")


def _stop(proc, datadir) -> None:
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    if datadir is not None:
        shutil.rmtree(datadir, ignore_errors=True)


def test_postgres_keeps_one_row_per_connection_and_the_old_timestamp():
    dsn, proc, datadir = _start_postgres()
    try:
        applied = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(MIGRATION)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=_pg_env(),
        )
        assert applied.returncode == 0, applied.stderr
        first = fold_context(
            company_id=COMPANY,
            pages=[
                _page("hubspot", {"results": [{"id": "42", "properties": {"owner_email": "ana@vocify.test"}}]}, "crm-A"),
                _page("pipedrive", {"data": [{"id": 42, "owner_id": {"email": "ana@vocify.test"}}]}, "crm-B"),
            ],
            members=MEMBERS,
        )
        assert _psql(dsn, upsert_statements(first)).returncode == 0
        failed = fold_context(
            company_id=COMPANY,
            pages=[_page("hubspot", {"error_kind": "timeout"}, "crm-A", observed_at="2026-09-22T12:00:00Z")],
            members=MEMBERS,
            previous=[row for row in first if row["connection_id"] == "crm-A"],
        )
        saved = _psql(dsn, upsert_statements(failed))
        assert saved.returncode == 0, saved.stderr
        counted = _psql(dsn, "SELECT count(*) FROM contact_priority_context;")
        assert "2" in counted.stdout
        shown = _psql(
            dsn,
            "SELECT coverage || ' ' || (observed_at AT TIME ZONE 'UTC')::text FROM contact_priority_context WHERE connection_id = 'crm-A';",
        )
        assert "unavailable" in shown.stdout
        assert "2026-09-22 09:00:00" in shown.stdout
        assert "12:00:00" not in shown.stdout
    finally:
        _stop(proc, datadir)


def test_both_providers_walk_pages_and_a_timeout_does_not_replace_the_cache():
    hubspot_pages = [
        {"results": [{"id": "1", "properties": {"owner_email": "ana@vocify.test"}}], "paging": {"next": {"after": "100"}}},
        {"results": [{"id": "2", "properties": {"owner_email": "ana@vocify.test"}}]},
    ]
    calls = []

    def fetch_hubspot(request):
        calls.append(request)
        return hubspot_pages.pop(0)

    collected = collect_assigned("hubspot", fetch_hubspot, connection_id="crm-A", observed_at="2026-09-22T09:00:00Z")
    assert calls[0]["path"] == "/crm/v3/objects/contacts/search"
    assert "after" not in calls[0]["json"]
    assert calls[1]["json"]["after"] == "100"
    assert collected["coverage"] == "complete"
    assert [item["contact_id"] for item in collected["items"]] == ["1", "2"]
    rows = fold_context(company_id=COMPANY, pages=[collected], members=MEMBERS)
    assert rows[0]["history_complete"] is True

    pipedrive_pages = [
        {"data": [{"id": 7, "owner_id": 4}], "additional_data": {"next_cursor": "p2"}},
        {"data": [{"id": 8, "owner_id": {"email": "ana@vocify.test"}}]},
    ]

    def fetch_pipedrive(request):
        assert request["path"] == "/persons"
        assert request["version"] == "v2"
        return pipedrive_pages.pop(0)

    pipedrive = collect_assigned("pipedrive", fetch_pipedrive, connection_id="crm-B", observed_at="2026-09-22T09:00:00Z")
    assert [item["contact_id"] for item in pipedrive["items"]] == ["7", "8"]
    assert pipedrive["items"][0]["owner_email"] is None

    stopped = collect_assigned(
        "hubspot",
        lambda _request: {"results": [{"id": "42", "properties": {}}], "paging": {"next": {"after": "9"}}},
        connection_id="crm-A",
        observed_at="2026-09-22T12:00:00Z",
        max_pages=1,
    )
    assert stopped["coverage"] == "partial"
    ranked = rank_candidates(snapshot_from_rows(
        fold_context(company_id=COMPANY, pages=[stopped], members=MEMBERS),
        connected=True,
    )["candidates"], NOW)
    assert ranked[0]["never_called"] is False

    previous = fold_context(company_id=COMPANY, pages=[collected], members=MEMBERS)

    def fail_second(request):
        if request["json"].get("after"):
            raise TimeoutError("crm")
        return {"results": [{"id": "9", "properties": {}}], "paging": {"next": {"after": "1"}}}

    failed = collect_assigned("hubspot", fail_second, connection_id="crm-A", observed_at="2026-09-22T12:00:00Z")
    kept = fold_context(company_id=COMPANY, pages=[failed], members=MEMBERS, previous=previous)
    assert kept[0]["observed_at"] == "2026-09-22T09:00:00Z"
    assert failed["items"] == []

