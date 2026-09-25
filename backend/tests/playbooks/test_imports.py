"""F08 imports: failures stay off the published playbook and never create a memo."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.playbooks import router as playbooks_router, set_playbook_store
from app.deps import get_membership
from app.services.company import Membership
from app.services.playbooks.imports import start_import
from app.services.playbooks.store import MemoryPlaybookStore


def test_import_from_another_company_is_not_found():
    store = MemoryPlaybookStore({}, {})
    store.save_import("co-a", {"import_id": "imp-a", "status": "ready", "draft": {"text": "secret"}}, None)
    assert store.get_import("co-b", "imp-a") is None
    assert store.get_import("co-a", "imp-a")["import_id"] == "imp-a"


def test_http_get_import_from_another_company_is_not_found():
    store = MemoryPlaybookStore({}, {})
    set_playbook_store(store)
    try:
        store.save_import(
            "co-a",
            {"import_id": "imp-a", "status": "ready", "draft": {"text": "secret"}},
            None,
        )
        app = FastAPI()
        app.include_router(playbooks_router)
        company = {"id": "co-b"}
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id=company["id"], user_id="u", role="owner", status="active",
        )
        client = TestClient(app)
        other = client.get("/api/v1/playbooks/imports/imp-a")
        assert other.status_code == 404
        company["id"] = "co-a"
        own = client.get("/api/v1/playbooks/imports/imp-a")
        assert own.status_code == 200
        assert own.json()["import_id"] == "imp-a"
    finally:
        set_playbook_store(None)


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


def test_text_becomes_a_revisable_draft():
    result = start_import(
        import_id="imp-text",
        kind="text",
        payload="Confirmar el problema antes del precio.",
        active_version_id=None,
    )
    assert result["status"] == "ready"
    assert result["published"] is False
    assert result["draft"]["text"] == "Confirmar el problema antes del precio."
    assert result["draft"]["source_ref"] == "text:imp-text"
    assert result["draft"]["contradictions"] == []


def test_member_can_read_playbooks_but_cannot_import():
    app = FastAPI()
    app.include_router(playbooks_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co", user_id="u", role="member", status="active",
    )
    client = TestClient(app)
    listed = client.get("/api/v1/playbooks")
    assert listed.status_code == 200
    assert isinstance(listed.json()["motions"], dict)
    denied = client.post(
        "/api/v1/playbooks/imports",
        json={"import_id": "imp-2", "kind": "text", "payload": "Hola", "active_version_id": "pv-2"},
    )
    assert denied.status_code == 403


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


def _pdf_bytes(text: str, password: str | None = None) -> bytes:
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
    })
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 200 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    if password:
        writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_a_real_pdf_becomes_a_draft_and_an_encrypted_one_does_not_replace_the_active_version():
    import base64

    payload = base64.b64encode(_pdf_bytes("Confirmar el problema")).decode("ascii")
    result = start_import(
        import_id="imp-real",
        kind="pdf",
        payload=payload,
        active_version_id="pv-2",
    )
    assert result["status"] == "ready"
    assert result["draft"]["text"] == "Confirmar el problema"
    assert "%PDF" not in result["draft"]["text"]
    assert result["draft"]["source_ref"] == "pdf:imp-real"
    assert result["published"] is False
    assert result["active_version_id"] == "pv-2"
    assert result["memo_id"] is None

    encrypted = base64.b64encode(_pdf_bytes("Secreto", password="secret")).decode("ascii")
    locked = start_import(
        import_id="imp-locked",
        kind="pdf",
        payload=encrypted,
        active_version_id="pv-2",
    )
    assert locked["status"] == "failed"
    assert locked["reason"] == "pdf_encrypted"
    assert locked["published"] is False
    assert locked["active_version_id"] == "pv-2"
    assert locked["draft"] is None


def test_audio_import_uses_stt_and_does_not_create_a_memo():
    from fastapi import FastAPI

    from app.api.playbooks import router as playbooks_router
    from app.api.playbooks import set_playbook_transcriber

    seen = {}

    def transcribe(payload: str) -> str:
        seen["payload"] = payload
        return "Confirmar el problema antes de hablar de precio."

    set_playbook_transcriber(transcribe)
    app = FastAPI()
    app.include_router(playbooks_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co", user_id="u", role="owner", status="active",
    )
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/playbooks/imports",
            json={"import_id": "imp-audio-http", "kind": "audio", "payload": "audio-bytes", "active_version_id": "pv-2"},
        )
        assert response.status_code == 200
        body = response.json()
        assert seen["payload"] == "audio-bytes"
        assert body["published"] is False
        assert body["memo_id"] is None
        assert body["crm_sync"] is False
        assert body["draft"]["source_ref"] == "audio:imp-audio-http"
        assert body["draft"]["text"].startswith("Confirmar el problema")
    finally:
        set_playbook_transcriber(None)


def test_a_contradiction_stays_a_draft_and_can_be_reopened():
    from app.api import playbooks as playbooks_api

    playbooks_api._MOTIONS.clear()
    playbooks_api._IMPORTS.clear()
    playbooks_api._LATEST.clear()
    playbooks_api._ACTIVATED.clear()
    app = FastAPI()
    app.include_router(playbooks_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co", user_id="u", role="owner", status="active",
    )
    client = TestClient(app)
    created = client.post(
        "/api/v1/playbooks/imports",
        json={
            "import_id": "imp-conflict",
            "kind": "text",
            "payload": "Nunca descuentes. Siempre cierra.",
            "active_version_id": "pv-2",
            "sales_motion_key": "discovery",
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["published"] is False
    assert body["active_version_unchanged"] is True
    assert body["active_version_id"] == "pv-2"
    assert body["draft"]["contradictions"] == ["siempre/nunca"]
    blocked = client.post("/api/v1/playbooks/discovery/publish")
    assert blocked.status_code == 409
    assert client.get("/api/v1/playbooks").json()["motions"].get("discovery") != "published"
    reopened = client.get("/api/v1/playbooks/imports/imp-conflict")
    assert reopened.status_code == 200
    assert reopened.json()["published"] is False
    assert reopened.json()["draft"]["text"].startswith("Nunca")
    cleaned = client.post(
        "/api/v1/playbooks/imports",
        json={
            "import_id": "imp-clean",
            "kind": "text",
            "payload": "Confirmar el problema antes del precio.",
            "sales_motion_key": "discovery",
        },
    )
    assert cleaned.status_code == 200
    published = client.post("/api/v1/playbooks/discovery/publish")
    assert published.status_code == 200
    assert published.json()["motions"]["discovery"] == "published"
