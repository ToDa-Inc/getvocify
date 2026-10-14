"""A real MCP client signing in: the SDK's own OAuth client (discovery, registration, PKCE, token exchange,
refresh) against this server, in-process. What Claude Code and other SDK-based clients run."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx2
from fastapi import FastAPI
from mcp import Client
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthClientMetadata, OAuthToken
from starlette.routing import Route

from app.api import mcp_access
from app.deps import get_supabase, get_user_id  # the real dependencies, before the db fixture patches get_supabase
from app.services.mcp import oauth
from app.services.mcp.server import build_server
from tests.mcp.conftest import M_PRICE, REP

MCP_URL = "https://api.getvocify.com/mcp"


class Memory:
    def __init__(self) -> None:
        self.tokens: OAuthToken | None = None
        self.client: OAuthClientInformationFull | None = None

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens):
        self.tokens = tokens

    async def get_client_info(self):
        return self.client

    async def set_client_info(self, info):
        self.client = info


async def test_the_sdk_client_discovers_registers_signs_in_and_reads_data(db):
    server = build_server()
    mcp_asgi = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        host="0.0.0.0",
    )
    app = FastAPI()
    app.include_router(mcp_access.oauth_router)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_user_id] = lambda: REP
    for path in ("/mcp", "/.well-known/oauth-protected-resource/mcp"):
        app.router.routes.append(Route(path, endpoint=mcp_asgi))
    app.router.routes.extend(oauth.routes())

    transport = httpx2.ASGITransport(app=app)
    landed: dict = {}

    async def redirect_handler(url: str) -> None:
        """What the user's browser does: open the authorize URL, land on the dashboard's consent page, press Allow."""
        async with httpx2.AsyncClient(transport=transport, base_url="https://api.getvocify.com") as browser:
            to_consent = await browser.get(url)
            assert to_consent.status_code == 302, to_consent.text
            consent_page = urlparse(to_consent.headers["location"])
            assert consent_page.path == "/oauth/consent"
            authorization_id = parse_qs(consent_page.query)["authorization_id"][0]
            allowed = await browser.post(
                f"/api/v1/oauth/authorizations/{authorization_id}/consent",
                json={"action": "approve"},
                headers={"Authorization": "Bearer dashboard-session"},
            )
            assert allowed.status_code == 200, allowed.text
            landed.update({k: v[0] for k, v in parse_qs(urlparse(allowed.json()["redirect_url"]).query).items()})

    async def callback_handler() -> AuthorizationCodeResult:
        return AuthorizationCodeResult(code=landed["code"], state=landed.get("state"))

    storage = Memory()
    auth = OAuthClientProvider(
        MCP_URL,
        OAuthClientMetadata(
            client_name="SDK test client",
            redirect_uris=["http://localhost:3118/callback"],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
        ),
        storage,
        redirect_handler,
        callback_handler,
    )
    http_client = httpx2.AsyncClient(transport=transport, base_url="https://api.getvocify.com", auth=auth)

    async with server.session_manager.run():
        async with Client(streamable_http_client(MCP_URL, http_client=http_client)) as client:
            tools = await client.list_tools()
            assert {t.name for t in tools.tools} == {"list_interactions", "get_interaction", "get_coaching", "ask_vocify", "get_ask_result"}
            result = await client.call_tool("list_interactions", {"limit": 5})
            rows = json.loads(result.content[0].text)["interactions"]
            assert M_PRICE in [row["id"] for row in rows]

    assert storage.tokens and storage.tokens.refresh_token and storage.client.client_name == "SDK test client"
    grants = next(r for r in db.tables["user_profiles"] if r["id"] == REP)["oauth_grants"]
    assert [g["name"] for g in grants.values()] == ["SDK test client"]
