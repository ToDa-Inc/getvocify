"""The desktop app sends its log by itself: one file per rep and platform, replaced each time."""

import os
from unittest.mock import MagicMock

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-diagnostics-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-diagnostics-32b")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import desktop_diagnostics
from app.deps import get_supabase, get_user_id

REP = "11111111-1111-1111-1111-111111111111"


def _client(supabase) -> TestClient:
    app = FastAPI()
    app.include_router(desktop_diagnostics.router)
    app.dependency_overrides[get_user_id] = lambda: REP
    app.dependency_overrides[get_supabase] = lambda: supabase
    return TestClient(app)


def test_the_log_replaces_the_reps_file_for_that_platform():
    supabase = MagicMock()
    res = _client(supabase).post("/api/v1/desktop/diagnostics", json={"platform": "win32", "version": "0.4.344", "log": "island: a pill\n"})
    assert res.status_code == 204
    supabase.storage.from_.assert_called_with("desktop-logs")
    kwargs = supabase.storage.from_.return_value.upload.call_args.kwargs
    assert kwargs["path"] == f"{REP}/win32.log"
    assert kwargs["file_options"]["upsert"] == "true"
    assert kwargs["file"].decode().endswith("island: a pill\n")


def test_a_failed_upload_never_fails_the_app():
    supabase = MagicMock()
    supabase.storage.from_.return_value.upload.side_effect = RuntimeError("storage down")
    res = _client(supabase).post("/api/v1/desktop/diagnostics", json={"platform": "darwin", "version": "1", "log": "x"})
    assert res.status_code == 204


def test_an_unknown_platform_or_a_huge_log_is_refused():
    client = _client(MagicMock())
    assert client.post("/api/v1/desktop/diagnostics", json={"platform": "linux", "version": "1", "log": "x"}).status_code == 422
    big = "x" * (desktop_diagnostics.MAX_LOG_CHARS + 1)
    assert client.post("/api/v1/desktop/diagnostics", json={"platform": "win32", "version": "1", "log": big}).status_code == 422
