"""F08 imports: failures stay off the published playbook and never create a memo."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.playbooks import router as playbooks_router
from app.deps import get_membership
from app.services.company import Membership
from app.services.playbooks.imports import start_import


def test_empty_pdf_fails_and_leaves_the_active_version():
    result = start_import(
        import_id="imp-1",
        kind="pdf",
        payload="%PDF-1.4 encrypted",
        active_version_id="pv-2",
    )
    assert result["status"] == "failed"
    assert result["reason"] == "pdf_has_no_text"
    assert result["active_version_unchanged"] is True
    assert result["published"] is False
    assert result["active_version_id"] == "pv-2"
    assert result["memo_id"] is None


def test_audio_becomes_a_draft_without_a_crm_memo():
    result = start_import(
        import_id="imp-audio",
        kind="audio",
        payload="bytes",
        active_version_id="pv-2",
        stt=lambda _raw: "Confirmar el problema antes de hablar de precio.",
    )
    assert result["status"] == "ready"
    assert result["draft"]["source_ref"] == "audio:imp-audio"
    assert result["memo_id"] is None
    assert result["crm_sync"] is False
    assert result["published"] is False


def test_retrying_the_same_import_does_not_publish_or_duplicate():
    first = start_import(import_id="imp-1", kind="text", payload="Paso 1", active_version_id="pv-2")
    second = start_import(
        import_id="imp-1",
        kind="text",
        payload="Paso distinto",
        active_version_id="pv-9",
        existing=first,
    )
    assert second["status"] == "ready"
    assert second["draft"]["text"] == "Paso 1"
    assert second["versions_created"] == 0
    assert second["published"] is False


def test_member_cannot_start_an_import():
    app = FastAPI()
    app.include_router(playbooks_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co", user_id="u", role="member", status="active",
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/playbooks/imports",
        json={"import_id": "imp-2", "kind": "text", "payload": "Hola", "active_version_id": "pv-2"},
    )
    assert response.status_code == 403
