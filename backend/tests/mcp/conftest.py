"""Drives the MCP server over HTTP, as a client does, against an in-memory database."""

from __future__ import annotations

import json
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-mcp-tests-32chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-mcp-tests-32chars")

import pytest
from starlette.testclient import TestClient

import app.api.mcp_access  # noqa: E402,F401 - binds the real get_supabase before the db fixture patches it
from tests.mcp.fake_db import FakeDB

COMPANY = "co-1"
OTHER_COMPANY = "co-2"
MANAGER, REP, TEAMMATE, OUTSIDER = "mgr-1", "rep-1", "rep-2", "out-1"

M_PRICE = "11111111-1111-4111-8111-111111111111"
M_MEETING = "22222222-2222-4222-8222-222222222222"
M_INTERNAL = "33333333-3333-4333-8333-333333333333"
M_PROCESSING = "44444444-4444-4444-8444-444444444444"
M_TEAMMATE = "55555555-5555-4555-8555-555555555555"

TRANSCRIPT = "\n".join(f"Rep: line {i} about pricing and next steps for Acme." for i in range(600))


def _memo(memo_id, user_id, created_at, *, status="approved", kind="call", motion="sdr", outcome=None, extraction=None, transcript=""):
    return {
        "id": memo_id,
        "user_id": user_id,
        "company_id": COMPANY,
        "status": status,
        "created_at": created_at,
        "capture_started_at": created_at,
        "interaction_kind": kind,
        "sales_motion_key": motion,
        "rep_outcome": outcome,
        "audio_duration": 312.4,
        "hubspot_contact_id": "c-ana" if user_id == REP else "c-bo",
        "hubspot_deal_id": None,
        "transcript": transcript,
        "extraction": extraction or {},
        "attendees": [],
    }


def _extraction(contact, company, summary, objections=(), competitors=()):
    return {
        "contactName": contact,
        "companyName": company,
        "summary": summary,
        "nextSteps": ["Send the proposal on Friday"],
        "competitors": list(competitors),
        "intelligence": {
            "version": 1,
            "status": "ready",
            "interest": "medium",
            "objections": [
                {"kind": "objection", "category": cat, "resolution": "open", "quote": quote, "evidence_refs": []}
                for cat, quote in objections
            ],
            "commitments": [{"text": "Send the proposal", "due_at": "2026-10-17", "origin": "rep"}],
            "evidence": [{"id": "ev1", "quote": "It's too expensive for us", "speaker_role": "prospect", "start_ms": 61000}],
        },
    }


def seed() -> FakeDB:
    return FakeDB(
        company_members=[
            {"id": "m-a", "company_id": COMPANY, "user_id": MANAGER, "role": "owner", "status": "active", "visibility": "own"},
            {"id": "m-b", "company_id": COMPANY, "user_id": REP, "role": "member", "status": "active", "visibility": "own"},
            {"id": "m-c", "company_id": COMPANY, "user_id": TEAMMATE, "role": "member", "status": "active", "visibility": "own"},
            {"id": "m-d", "company_id": OTHER_COMPANY, "user_id": OUTSIDER, "role": "owner", "status": "active", "visibility": "own"},
        ],
        user_profiles=[{"id": uid} for uid in (MANAGER, REP, TEAMMATE, OUTSIDER)],
        company_feature_flags=[
            {"company_id": COMPANY, "flag": "MCP_ENABLED", "enabled": True},
            {"company_id": OTHER_COMPANY, "flag": "MCP_ENABLED", "enabled": False},
        ],
        memo_scores=[
            {"memo_id": M_PRICE, "revision_seq": 1, "input_revision": "r1", "created_at": "2026-10-10T10:05:00+00:00",
             "score": {"value": 8, "adherence": 0.8, "coverage": 0.5, "strengths": ["Opened with a frame"], "improvements": ["Ask a follow-up"]}},
            {"memo_id": M_MEETING, "revision_seq": 1, "input_revision": "r1", "created_at": "2026-10-09T10:05:00+00:00",
             "score": {"value": None, "adherence": None, "coverage": 0.0}},
        ],
        memos=[
            _memo(
                M_PRICE, REP, "2026-10-10T10:00:00+00:00", outcome="follow_up", transcript=TRANSCRIPT,
                extraction=_extraction("Ana", "Acme", "Pricing call with Acme.\nMore detail.", [("price", "It's too expensive")], ["Gong"]),
            ),
            _memo(
                M_MEETING, REP, "2026-10-09T10:00:00+00:00", status="pending_review", kind="meeting", outcome="meeting_booked",
                extraction=_extraction("Luis", "Beta", "Discovery meeting with Beta.", [("timing", "Not this quarter")]),
            ),
            _memo(M_INTERNAL, REP, "2026-10-08T10:00:00+00:00", motion="internal", extraction=_extraction("Marta", "Vocify", "Internal sync.")),
            _memo(M_PROCESSING, REP, "2026-10-11T10:00:00+00:00", status="processing"),
            _memo(
                M_TEAMMATE, TEAMMATE, "2026-10-07T10:00:00+00:00",
                extraction=_extraction("Bo", "Gamma", "Call with Gamma about price.", [("price", "Cheaper elsewhere")]),
            ),
        ],
    )


@pytest.fixture
def db(monkeypatch):
    from app.services import feature_flags
    from app.services.company import CompanyService
    from app.services.mcp import access

    database = seed()
    monkeypatch.setattr("app.deps.get_supabase", lambda: database)

    def list_members(self, company_id, **_k):
        return [
            {"user_id": r["user_id"], "status": r["status"], "role": r["role"], "full_name": f"Name {r['user_id']}", "email": f"{r['user_id']}@x.test"}
            for r in database.tables["company_members"]
            if r["company_id"] == company_id
        ]

    monkeypatch.setattr(CompanyService, "list_members", list_members)
    monkeypatch.setattr(CompanyService, "get_company", lambda self, company_id: {"id": company_id, "name": "Acme Sales"})
    from app.services.mcp import oauth

    feature_flags.clear_cache()
    access.reset_rate_limits()
    access._paywalled.clear()
    oauth._grants_cache.clear()
    oauth._used_codes.clear()
    yield database
    feature_flags.clear_cache()
    access.reset_rate_limits()
    oauth._grants_cache.clear()
    oauth._used_codes.clear()


@pytest.fixture
def mcp_client(db):
    from mcp.server.transport_security import TransportSecuritySettings

    from app.services.mcp.server import build_server

    app = build_server().streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        host="0.0.0.0",
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture
def key_for(db):
    """A real API key for a user, generated the way Settings does."""
    from app.services.mcp import api_keys

    return lambda user_id: api_keys.generate_key(db, user_id)["key"]


@pytest.fixture
def oauth_token_for(db):
    """An access token as the OAuth server would issue it after the user allowed an app."""
    from app.services.mcp import oauth

    def mint(user_id: str, app: str = "Claude") -> str:
        key, chain = oauth.grant_key(app, "https://claude.ai/cb"), "chain-1"
        row = next(r for r in db.tables["user_profiles"] if r["id"] == user_id)
        row["oauth_grants"] = {key: {"name": app, "host": "claude.ai", "at": "2026-10-14T10:00:00+00:00", "chains": {chain: {"rt": "j0", "at": "x"}}}}
        oauth._grants_cache.clear()
        return oauth._issue(user_id, key, chain, "client", "j0").access_token

    return mint


HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": "2025-11-25"}


def rpc(client, token, method, params=None, *, request_id=1):
    headers = dict(HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}, headers=headers)


def call(client, token, tool, arguments=None):
    """(is_error, body): body is the parsed JSON a tool returned, or the error text."""
    response = rpc(client, token, "tools/call", {"name": tool, "arguments": arguments or {}})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    text = result["content"][0]["text"]
    if result.get("isError"):
        return True, text
    return False, json.loads(text)
