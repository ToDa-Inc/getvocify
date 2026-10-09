"""Lista 4 E6: a rep (member) opens Settings -> Glossary and Usage.

The company glossary is readable by every member; adding, editing and deleting terms
stays with the Head of Sales (owner/admin), so the member's page is read-only. Usage is
always the caller's own memos.
"""

import os
from unittest.mock import MagicMock

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-glossary-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-glossary-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import glossary as glossary_api
from app.api import memos as memos_api
from app.deps import get_supabase, get_user_id
from app.services.company import CompanyService, Membership
from app.services.glossary import GlossaryService

MEMBER = "11111111-1111-1111-1111-111111111111"
COMPANY = "99999999-9999-9999-9999-999999999999"
TERMS = [{"id": "t1", "target_word": "Vocify", "phonetic_hints": [], "boost_factor": 5, "category": "Company"}]


def _client(supabase=None) -> TestClient:
    app = FastAPI()
    app.include_router(glossary_api.router)
    app.include_router(memos_api.router)
    app.dependency_overrides[get_user_id] = lambda: MEMBER
    app.dependency_overrides[get_supabase] = lambda: supabase or MagicMock()
    return TestClient(app)


@pytest.fixture
def membership(monkeypatch):
    def use(role: str):
        monkeypatch.setattr(
            CompanyService,
            "require_membership",
            lambda self, user_id: Membership(
                id="m1", company_id=COMPANY, user_id=user_id, role=role, status="active"
            ),
        )

    return use


@pytest.fixture
def glossary(monkeypatch):
    async def read(self, user_id):
        return [dict(item) for item in TERMS]

    written = []

    async def write(self, user_id, items):
        written.append(items)
        return items

    monkeypatch.setattr(GlossaryService, "get_user_glossary", read)
    monkeypatch.setattr(GlossaryService, "update_glossary", write)
    return written


def test_member_reads_the_company_glossary(membership, glossary):
    membership("member")
    response = _client().get("/api/v1/glossary")
    assert response.status_code == 200
    assert [item["target_word"] for item in response.json()] == ["Vocify"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/v1/glossary", {"target_word": "Nuevo", "phonetic_hints": ["nuevo"]}),
        ("patch", "/api/v1/glossary/t1", {"category": "Product"}),
        ("delete", "/api/v1/glossary/t1", None),
        ("post", "/api/v1/glossary/bulk-add", {"items": [{"target_word": "Nuevo", "phonetic_hints": ["nuevo"]}]}),
    ],
)
def test_member_cannot_change_the_glossary(membership, glossary, method, path, body):
    membership("member")
    client = _client()
    response = client.request(method.upper(), path, json=body)
    assert response.status_code == 403
    assert glossary == []


def test_admin_still_edits_the_glossary(membership, glossary):
    membership("admin")
    response = _client().patch("/api/v1/glossary/t1", json={"category": "Product"})
    assert response.status_code == 200
    assert glossary and glossary[0][0]["category"] == "Product"


def test_member_reads_only_their_own_usage():
    supabase = MagicMock()
    query = supabase.table.return_value.select.return_value
    query.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": "a", "status": "approved", "created_at": "2026-09-01T10:00:00+00:00", "audio_duration": 60, "extraction": {}},
    ]
    response = _client(supabase).get("/api/v1/memos/usage")
    assert response.status_code == 200
    assert response.json()["total_memos"] == 1
    supabase.table.assert_called_with("memos")
    query.eq.assert_called_once_with("user_id", MEMBER)
