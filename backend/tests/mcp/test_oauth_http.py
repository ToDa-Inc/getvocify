"""Sign in with a Vocify account, over HTTP the way Claude.ai or ChatGPT does it: register, authorize, the
dashboard's consent, the token exchange with PKCE, refresh, and disconnect. Then the token is used on /mcp."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from urllib.parse import parse_qs, urlparse

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import mcp_access
from app.deps import get_supabase, get_user_id  # the real dependencies, before the db fixture patches get_supabase
from app.services.mcp import access, oauth
from tests.mcp.conftest import M_PRICE, OUTSIDER, REP, TEAMMATE, call, rpc

CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
MCP_URL = "https://api.getvocify.com/mcp"


@pytest.fixture
def server(db):
    """The API's OAuth routes plus the dashboard's consent routes. `who` is the dashboard user answering."""
    who = {"id": REP}
    app = FastAPI()
    app.include_router(mcp_access.router)
    app.include_router(mcp_access.oauth_router)
    app.router.routes.extend(oauth.routes())
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_user_id] = lambda: who["id"]
    client = TestClient(app, follow_redirects=False, headers={"Authorization": "Bearer dashboard-session"})
    client.who = who
    return client


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode().rstrip("=")


def register(server, *, name="Claude", redirect=CLAUDE_CALLBACK):
    response = server.post(
        "/oauth/register",
        json={
            "client_name": name,
            "redirect_uris": [redirect],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["client_id"]


def authorize(server, client_id, *, redirect=CLAUDE_CALLBACK, challenge, state="st-1", resource=MCP_URL):
    return server.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id, "redirect_uri": redirect, "code_challenge": challenge,
            "code_challenge_method": "S256", "state": state, **({"resource": resource} if resource else {}),
        },
    )


def authorization_id(response) -> str:
    assert response.status_code == 302, response.text
    return parse_qs(urlparse(response.headers["location"]).query)["authorization_id"][0]


def connect(server, *, name="Claude", redirect=CLAUDE_CALLBACK, user=REP):
    """The whole sign-in. Returns (token response body, client_id, code verifier)."""
    client_id = register(server, name=name, redirect=redirect)
    verifier, challenge = pkce()
    aid = authorization_id(authorize(server, client_id, redirect=redirect, challenge=challenge))
    server.who["id"] = user
    consent = server.post(f"/api/v1/oauth/authorizations/{aid}/consent", json={"action": "approve"})
    assert consent.status_code == 200, consent.text
    back = urlparse(consent.json()["redirect_url"])
    query = parse_qs(back.query)
    assert f"{back.scheme}://{back.netloc}{back.path}" == redirect and query["state"] == ["st-1"]
    token = exchange_code(server, client_id, query["code"][0], verifier, redirect)
    assert token.status_code == 200, token.text
    return token.json(), client_id, verifier


def exchange_code(server, client_id, code, verifier, redirect=CLAUDE_CALLBACK):
    return server.post(
        "/oauth/token",
        data={"grant_type": "authorization_code", "code": code, "code_verifier": verifier, "client_id": client_id, "redirect_uri": redirect},
    )


def refresh(server, client_id, refresh_token):
    return server.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id})


def grants_of(db, user_id):
    return next(r for r in db.tables["user_profiles"] if r["id"] == user_id).get("oauth_grants") or {}


# ----- discovery --------------------------------------------------------------------------------------


def test_the_metadata_points_at_this_server_and_asks_for_pkce(server):
    body = server.get("/.well-known/oauth-authorization-server").json()
    assert body["issuer"] == "https://api.getvocify.com"
    assert body["authorization_endpoint"].endswith("/oauth/authorize") and body["token_endpoint"].endswith("/oauth/token")
    assert body["registration_endpoint"].endswith("/oauth/register")
    assert body["code_challenge_methods_supported"] == ["S256"] and body["token_endpoint_auth_methods_supported"] == ["none"]


# ----- the happy path ---------------------------------------------------------------------------------


def test_signing_in_gives_a_token_that_reads_the_users_own_data(server, mcp_client):
    token, _, _ = connect(server)
    assert token["token_type"] == "Bearer" and token["expires_in"] == 3600 and token["refresh_token"]
    _, listed = call(mcp_client, token["access_token"], "list_interactions")
    assert M_PRICE in [row["id"] for row in listed["interactions"]]


def test_a_connected_app_is_listed_and_disconnecting_it_stops_its_tokens(server, mcp_client):
    token, _, _ = connect(server)
    listed = server.get("/api/v1/oauth/grants").json()["grants"]
    assert [g["client"]["client_name"] for g in listed] == ["Claude"] and listed[0]["client"]["client_uri"] == "claude.ai"
    assert rpc(mcp_client, token["access_token"], "tools/list").status_code == 200

    assert server.delete("/api/v1/oauth/grants", params={"client_id": listed[0]["client"]["client_id"]}).status_code == 204
    assert server.get("/api/v1/oauth/grants").json()["grants"] == []
    assert rpc(mcp_client, token["access_token"], "tools/list").status_code == 401


def test_reconnecting_the_same_app_is_one_entry_and_both_connections_keep_working(server, mcp_client, db):
    first, _, _ = connect(server)
    second, _, _ = connect(server)
    assert len(grants_of(db, REP)) == 1 and len(next(iter(grants_of(db, REP).values()))["chains"]) == 2
    assert rpc(mcp_client, first["access_token"], "tools/list").status_code == 200
    assert rpc(mcp_client, second["access_token"], "tools/list").status_code == 200


def test_consent_says_who_is_asking_and_whether_we_recognise_them(server):
    claude = authorization_id(authorize(server, register(server), challenge=pkce()[1]))
    shown = server.get(f"/api/v1/oauth/authorizations/{claude}").json()
    assert shown["client"]["client_name"] == "Claude" and shown["redirect_uri"] == CLAUDE_CALLBACK and shown["known"] is True

    other = "https://evil.example/callback"
    stranger = authorization_id(authorize(server, register(server, name="Claude", redirect=other), redirect=other, challenge=pkce()[1]))
    assert server.get(f"/api/v1/oauth/authorizations/{stranger}").json()["known"] is False


def test_denying_sends_the_app_back_with_access_denied(server):
    aid = authorization_id(authorize(server, register(server), challenge=pkce()[1]))
    url = server.post(f"/api/v1/oauth/authorizations/{aid}/consent", json={"action": "deny"}).json()["redirect_url"]
    assert parse_qs(urlparse(url).query) == {"error": ["access_denied"], "state": ["st-1"]}


# ----- refresh ------------------------------------------------------------------------------------------


def test_a_refresh_gives_a_new_pair_and_the_new_access_token_works(server, mcp_client):
    token, client_id, _ = connect(server)
    renewed = refresh(server, client_id, token["refresh_token"])
    assert renewed.status_code == 200
    body = renewed.json()
    assert body["refresh_token"] != token["refresh_token"]
    assert rpc(mcp_client, body["access_token"], "tools/list").status_code == 200


def test_the_old_refresh_token_still_works_for_a_moment_and_gets_the_current_one(server, db):
    token, client_id, _ = connect(server)
    refresh(server, client_id, token["refresh_token"])
    again = refresh(server, client_id, token["refresh_token"])  # two refreshes in flight
    assert again.status_code == 200
    chain = next(iter(next(iter(grants_of(db, REP).values()))["chains"].values()))
    claims = pyjwt.decode(again.json()["refresh_token"], options={"verify_signature": False})
    assert claims["jti"] == chain["rt"]  # the current token, not a new rotation


def test_an_old_refresh_token_replayed_later_ends_that_connection_only(server, mcp_client, db):
    first, client_id, _ = connect(server)
    other, _, _ = connect(server)
    refresh(server, client_id, first["refresh_token"])
    for grant in grants_of(db, REP).values():
        for chain in grant["chains"].values():
            chain["until"] = 0  # the grace is over
    oauth._grants_cache.clear()

    replay = refresh(server, client_id, first["refresh_token"])
    assert replay.status_code == 400 and replay.json()["error"] == "invalid_grant"
    assert rpc(mcp_client, first["access_token"], "tools/list").status_code == 401
    assert rpc(mcp_client, other["access_token"], "tools/list").status_code == 200  # the other device is untouched


def test_a_refresh_token_does_not_belong_to_another_client(server):
    token, _, _ = connect(server)
    assert refresh(server, register(server, name="Other"), token["refresh_token"]).status_code == 400


# ----- what must not work ---------------------------------------------------------------------------------


def test_a_wrong_pkce_verifier_is_refused(server):
    client_id = register(server)
    _, challenge = pkce()
    aid = authorization_id(authorize(server, client_id, challenge=challenge))
    code = parse_qs(urlparse(server.post(f"/api/v1/oauth/authorizations/{aid}/consent", json={"action": "approve"}).json()["redirect_url"]).query)["code"][0]
    wrong = exchange_code(server, client_id, code, pkce()[0])
    assert wrong.status_code == 400 and wrong.json()["error"] == "invalid_grant"


def test_a_code_works_once(server):
    client_id = register(server)
    verifier, challenge = pkce()
    aid = authorization_id(authorize(server, client_id, challenge=challenge))
    code = parse_qs(urlparse(server.post(f"/api/v1/oauth/authorizations/{aid}/consent", json={"action": "approve"}).json()["redirect_url"]).query)["code"][0]
    assert exchange_code(server, client_id, code, verifier).status_code == 200
    assert exchange_code(server, client_id, code, verifier).status_code == 400


def test_a_code_is_for_the_redirect_uri_it_was_asked_with(server):
    client_id = register(server)
    verifier, challenge = pkce()
    aid = authorization_id(authorize(server, client_id, challenge=challenge))
    code = parse_qs(urlparse(server.post(f"/api/v1/oauth/authorizations/{aid}/consent", json={"action": "approve"}).json()["redirect_url"]).query)["code"][0]
    assert exchange_code(server, client_id, code, verifier, redirect="https://claude.ai/other").status_code == 400


def test_another_clients_code_is_refused(server):
    client_id, other_client = register(server), register(server, name="Other")
    verifier, challenge = pkce()
    aid = authorization_id(authorize(server, client_id, challenge=challenge))
    code = parse_qs(urlparse(server.post(f"/api/v1/oauth/authorizations/{aid}/consent", json={"action": "approve"}).json()["redirect_url"]).query)["code"][0]
    assert exchange_code(server, other_client, code, verifier).status_code == 400


def test_an_unregistered_or_tampered_client_cannot_start_a_sign_in(server):
    client_id = register(server)
    _, challenge = pkce()
    assert authorize(server, client_id + "x", challenge=challenge).status_code == 400
    assert authorize(server, "not-a-client", challenge=challenge).status_code == 400
    assert authorize(server, client_id, redirect="https://evil.example/cb", challenge=challenge).status_code == 400  # not registered


def test_a_resource_other_than_this_server_is_refused(server):
    response = authorize(server, register(server), challenge=pkce()[1], resource="https://other.example/mcp")
    assert response.status_code == 302 and parse_qs(urlparse(response.headers["location"]).query)["error"] == ["invalid_request"]


def test_a_forged_or_expired_consent_request_is_gone(server):
    assert server.get("/api/v1/oauth/authorizations/not-a-request").status_code == 404
    forged = pyjwt.encode({"use": "authreq", "cid": "x", "cn": "Claude", "ru": CLAUDE_CALLBACK, "rue": True, "cc": "c", "exp": int(time.time()) + 60, "iat": 0}, "wrong-key", algorithm="HS256")
    assert server.post(f"/api/v1/oauth/authorizations/{forged}/consent", json={"action": "approve"}).status_code == 404
    expired = oauth._sign("authreq", {"cid": "x", "cn": "Claude", "ru": CLAUDE_CALLBACK, "rue": True, "cc": "c"}, -10)
    assert server.get(f"/api/v1/oauth/authorizations/{expired}").status_code == 404


def test_a_workspace_with_ai_agents_off_cannot_allow_an_app(server):
    aid = authorization_id(authorize(server, register(server), challenge=pkce()[1]))
    server.who["id"] = OUTSIDER  # their workspace has MCP off
    response = server.post(f"/api/v1/oauth/authorizations/{aid}/consent", json={"action": "approve"})
    assert response.status_code == 409 and "turn it on" in response.json()["detail"]


@pytest.mark.parametrize(
    "redirect, ok",
    [
        (CLAUDE_CALLBACK, True),
        ("http://localhost:3118/callback", True),
        ("http://127.0.0.1:8080/cb", True),
        ("cursor://anysphere.cursor-retrieval/oauth/callback", True),
        ("http://evil.example/cb", False),
        ("javascript:alert(1)", False),
        ("https://claude.ai/cb#frag", False),
        ("data:text/html,x", False),
    ],
)
def test_registration_only_accepts_safe_redirect_uris(server, redirect, ok):
    response = server.post("/oauth/register", json={"client_name": "App", "redirect_uris": [redirect]})
    assert (response.status_code == 201) is ok, response.text
    if not ok:
        assert response.json()["error"] == "invalid_client_metadata"


def test_registration_needs_redirect_uris_and_stores_nothing(server, db):
    assert server.post("/oauth/register", json={"client_name": "App"}).status_code == 400
    assert server.post("/oauth/register", content=b"not json").status_code == 400
    register(server)
    assert all(not r.get("oauth_grants") for r in db.tables["user_profiles"])


# ----- the tokens themselves ---------------------------------------------------------------------------------


def test_tokens_cannot_stand_in_for_each_other(server, mcp_client):
    token, client_id, _ = connect(server)
    assert rpc(mcp_client, token["refresh_token"], "tools/list").status_code == 401  # a refresh token is not an access token
    assert refresh(server, client_id, token["access_token"]).status_code == 400  # nor the other way round


def test_an_access_token_for_another_audience_or_expired_or_forged_is_refused(server, mcp_client, oauth_token_for):
    oauth_token_for(REP)
    key = next(iter(next(r for r in server.app.dependency_overrides[get_supabase]().tables["user_profiles"] if r["id"] == REP)["oauth_grants"]))
    claims = {"iss": access.issuer_url(), "aud": access.server_url(), "sub": REP, "gk": key, "ch": "chain-1"}
    assert rpc(mcp_client, oauth._sign("at", claims, 600), "tools/list").status_code == 200
    assert rpc(mcp_client, oauth._sign("at", {**claims, "aud": "https://other.example/mcp"}, 600), "tools/list").status_code == 401
    assert rpc(mcp_client, oauth._sign("at", claims, -60), "tools/list").status_code == 401
    forged = pyjwt.encode({**claims, "use": "at", "iat": 0, "exp": int(time.time()) + 600}, "not-our-key", algorithm="HS256")
    assert rpc(mcp_client, forged, "tools/list").status_code == 401


def test_a_user_only_reads_their_own_data_through_a_token(server, mcp_client):
    token, _, _ = connect(server, user=TEAMMATE)
    _, listed = call(mcp_client, token["access_token"], "list_interactions")
    assert [row["id"] for row in listed["interactions"]] != [] and M_PRICE not in [row["id"] for row in listed["interactions"]]
