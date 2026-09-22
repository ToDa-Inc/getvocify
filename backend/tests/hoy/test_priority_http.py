"""F04 list: empty, partial and disconnected stay different, and another owner stays out."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-hoy-32bytes++")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import contact_priorities as api
from app.deps import get_membership
from app.services.company import Membership
from app.services.hoy.context import build_priority_page

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


def _client(user_id: str, role: str = "member") -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id=user_id, role=role, status="active",
    )
    return TestClient(app)


def setup_function():
    api._SNAPSHOTS.clear()


def test_no_snapshot_is_not_an_empty_complete_list():
    body = _client("user-a").get("/api/v1/contact-priorities").json()
    assert body["items"] == []
    assert body["coverage"] == "unavailable"
    assert body["title"] == "Conecta tu CRM para ver a quién contactar"
    assert "No hay contactos prioritarios" not in body["title"]


def test_complete_empty_partial_empty_and_foreign_owner():
    api._SNAPSHOTS[("co-1", "user-a")] = {
        "connected": True,
        "coverage": "complete",
        "assigned": True,
        "observed_at": "2026-09-22T09:00:00Z",
        "candidates": [],
    }
    empty = _client("user-a").get("/api/v1/contact-priorities").json()
    assert empty["title"].startswith("No hay contactos prioritarios ahora")
    assert empty["action"] == "Abrir contactos en CRM"

    api._SNAPSHOTS[("co-1", "user-a")] = {
        "connected": True,
        "coverage": "partial",
        "candidates": [],
        "observed_at": "2026-09-22T09:00:00Z",
    }
    partial = _client("user-a").get("/api/v1/contact-priorities").json()
    assert partial["title"] == "Falta parte del historial"
    assert "prospectar" not in partial["title"]

    api._SNAPSHOTS[("co-1", "user-a")] = {
        "connected": True,
        "coverage": "complete",
        "candidates": [
            {"connection_id": "crm-A", "contact_id": "1", "owner_user_id": "user-b", "coverage": "complete", "last_call_at": None},
            {"connection_id": "crm-A", "contact_id": "2", "owner_user_id": "user-a", "owner_ambiguous": True, "coverage": "complete"},
            {
                "connection_id": "crm-A",
                "contact_id": "42",
                "deal_id": "deal-7",
                "owner_user_id": "user-a",
                "coverage": "complete",
                "pain_confirmed": True,
                "pain_at": "2026-09-20T10:00:00Z",
                "evidence_refs": ["ev-1"],
            },
        ],
    }
    page = build_priority_page(
        snapshot=api._SNAPSHOTS[("co-1", "user-a")],
        user_id="user-a",
        role="member",
        now=NOW,
    )
    assert [row["contact_id"] for row in page["items"]] == ["42"]
    assert page["items"][0]["reason"].startswith("Confirmó el problema")
    assert "Tier" not in page["items"][0]["reason"]
