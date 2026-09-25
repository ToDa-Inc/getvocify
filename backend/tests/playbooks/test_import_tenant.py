"""Playbook imports must not leak across companies."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbook-import")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbook-import")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import playbooks as playbooks_api
from app.api.playbooks import set_playbook_store
from app.deps import get_membership
from app.services.company import Membership
from app.services.playbooks.store import MemoryPlaybookStore

COMPANY_A = "11111111-1111-1111-1111-111111111111"
COMPANY_B = "22222222-2222-2222-2222-222222222222"
IMPORT_ID = "import-secret-1"


def test_get_import_returns_only_the_callers_company():
    store = MemoryPlaybookStore(
        motions={},
        imports={
            IMPORT_ID: {
                "import_id": IMPORT_ID,
                "company_id": COMPANY_A,
                "status": "ready",
                "draft": {"steps": [{"title": "Paso 1"}]},
            }
        },
    )
    set_playbook_store(store)
    app = FastAPI()
    app.include_router(playbooks_api.router)

    def member(company_id: str):
        return Membership(
            id="m",
            company_id=company_id,
            user_id="user-a",
            role="admin",
            status="active",
        )

    app.dependency_overrides[get_membership] = lambda: member(COMPANY_A)
    client = TestClient(app)
    own = client.get(f"/api/v1/playbooks/imports/{IMPORT_ID}").json()
    assert own["import_id"] == IMPORT_ID

    app.dependency_overrides[get_membership] = lambda: member(COMPANY_B)
    blocked = client.get(f"/api/v1/playbooks/imports/{IMPORT_ID}")
    assert blocked.status_code == 404
