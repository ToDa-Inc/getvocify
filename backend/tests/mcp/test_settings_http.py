"""Settings → AI agents over HTTP: the workspace switches, a user's key, an admin revoking one, OAuth consent."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_supabase, get_user_id  # the real dependencies, before the db fixture patches get_supabase
from tests.mcp.conftest import MANAGER, OUTSIDER, REP, TEAMMATE, call


@pytest.fixture
def as_user(db):
    from app.api import mcp_access

    def client_for(user_id: str) -> TestClient:
        app = FastAPI()
        app.include_router(mcp_access.router)
        app.include_router(mcp_access.oauth_router)
        app.dependency_overrides[get_supabase] = lambda: db
        app.dependency_overrides[get_user_id] = lambda: user_id
        return TestClient(app, headers={"Authorization": "Bearer session-token"})

    return client_for


def test_a_rep_sees_their_key_status_but_not_the_member_list(as_user):
    body = as_user(REP).get("/api/v1/mcp/settings").json()
    assert body["enabled"] is True and body["transcripts_enabled"] is False
    assert body["key"] == {"has_key": False, "prefix": None, "created_at": None}
    assert body["server_url"].endswith("/mcp") and "members" not in body


def test_a_key_is_shown_once_then_only_its_prefix(as_user, mcp_client):
    client = as_user(REP)
    created = client.post("/api/v1/mcp/key").json()
    assert created["key"].startswith("vk_") and created["has_key"] is True
    status = client.get("/api/v1/mcp/settings").json()["key"]
    assert status["prefix"] == created["key"][:10] and "key" not in status
    assert call(mcp_client, created["key"], "list_interactions")[0] is False


def test_no_key_while_the_workspace_has_mcp_off(as_user):
    response = as_user(OUTSIDER).post("/api/v1/mcp/key")
    assert response.status_code == 409


def test_only_owners_and_admins_change_the_switches(as_user):
    assert as_user(REP).patch("/api/v1/mcp/settings", json={"transcripts_enabled": True}).status_code == 403
    body = as_user(MANAGER).patch("/api/v1/mcp/settings", json={"transcripts_enabled": True}).json()
    assert body["transcripts_enabled"] is True
    assert as_user(REP).get("/api/v1/mcp/settings").json()["transcripts_enabled"] is True


def test_turning_mcp_off_stops_every_key(as_user, mcp_client):
    key = as_user(REP).post("/api/v1/mcp/key").json()["key"]
    as_user(MANAGER).patch("/api/v1/mcp/settings", json={"enabled": False})
    is_error, text = call(mcp_client, key, "list_interactions")
    assert is_error and "turned off" in text


def test_an_admin_sees_who_has_a_key_and_can_revoke_it(as_user, mcp_client):
    key = as_user(TEAMMATE).post("/api/v1/mcp/key").json()["key"]
    members = {m["user_id"]: m for m in as_user(MANAGER).get("/api/v1/mcp/settings").json()["members"]}
    assert members[TEAMMATE]["has_key"] is True and members[REP]["has_key"] is False
    assert as_user(REP).delete(f"/api/v1/mcp/members/{TEAMMATE}/key").status_code == 403
    assert as_user(MANAGER).delete(f"/api/v1/mcp/members/{OUTSIDER}/key").status_code == 404
    assert as_user(MANAGER).delete(f"/api/v1/mcp/members/{TEAMMATE}/key").status_code == 204
    from tests.mcp.conftest import rpc

    assert rpc(mcp_client, key, "tools/list").status_code == 401


def test_a_user_revokes_their_own_key(as_user, mcp_client):
    from tests.mcp.conftest import rpc

    client = as_user(REP)
    key = client.post("/api/v1/mcp/key").json()["key"]
    assert client.delete("/api/v1/mcp/key").status_code == 204
    assert rpc(mcp_client, key, "tools/list").status_code == 401


def test_consent_forwards_to_supabase_with_the_users_own_token(as_user, monkeypatch):
    sent = []

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, method, url, headers=None, json=None, params=None):
            sent.append((method, url, headers, json))
            return httpx.Response(200, json={"redirect_url": "https://claude.ai/api/mcp/auth_callback?code=abc"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    body = as_user(REP).post("/api/v1/oauth/authorizations/auth-1/consent", json={"action": "approve"}).json()
    assert body["redirect_url"].startswith("https://claude.ai/")
    method, url, headers, payload = sent[0]
    assert method == "POST" and url.endswith("/auth/v1/oauth/authorizations/auth-1/consent")
    assert headers["Authorization"] == "Bearer session-token" and payload == {"action": "approve"}


def test_a_supabase_error_keeps_its_status(as_user, monkeypatch):
    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, *a, **k):
            return httpx.Response(404, json={"msg": "OAuth server is not enabled", "error_code": "oauth_server_disabled"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    response = as_user(REP).get("/api/v1/oauth/authorizations/auth-1")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "oauth_server_disabled"
