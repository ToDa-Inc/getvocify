"""Sign in with a Vocify account, for the MCP server: an OAuth 2.1 authorization server inside the API.

Claude.ai, Claude Desktop connectors and ChatGPT connect with this (they cannot send a custom API key). It is
the SDK's own authorize and token handlers (PKCE, redirect checks, error shapes) over a provider that keeps no
tables:

- A client id, a consent request, an authorization code, an access token and a refresh token are all signed
  tokens (HS256, a key derived from JWT_SECRET, one `use` claim each so none can stand in for another).
- The only stored state is `user_profiles.oauth_grants`, one JSON column: the apps this user connected, and for
  each connection (Claude on the web, Claude Desktop...) the id of its current refresh token. Disconnecting an app
  deletes its entry, and every token it holds stops working.
- Access tokens last an hour and are checked against that column (cached 30 s); refresh tokens last 90 days and
  rotate on every use. An old one replayed past a 60 s grace ends that one connection.

Endpoints (on the API host): /.well-known/oauth-authorization-server, /oauth/register, /oauth/authorize (sends
the browser to the dashboard's consent page), /oauth/token. Consent itself is /api/v1/oauth/* (api/mcp_access).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import anyio
import jwt as pyjwt
from pydantic import AnyUrl, ValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, request_response

from mcp.server.auth.handlers.authorize import AuthorizationHandler
from mcp.server.auth.handlers.metadata import MetadataHandler
from mcp.server.auth.handlers.token import TokenHandler
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthMetadata, OAuthToken

from app.config import settings
from app.services.mcp import access
from app.services.ttl_cache import TtlCache

logger = logging.getLogger(__name__)

ACCESS_TTL = 3600
REFRESH_TTL = 90 * 86400
CODE_TTL = 60
REQUEST_TTL = 600
REFRESH_GRACE = 60  # an old refresh token still works this long after it was rotated (two refreshes in flight)
MAX_CONNECTIONS = 5  # per app: web, desktop, mobile, a second browser
CLIENT_TTL = 365 * 86400
MAX_REDIRECT_URIS = 10
_BAD_SCHEMES = frozenset({"javascript", "data", "file", "vbscript", "blob", "about", "ftp"})
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "[::1]", "::1"})
# Where an app's sign-in normally lands. Anything else gets a warning on the consent screen: the app's name is
# whatever it called itself when it registered.
_KNOWN_HOSTS = frozenset({"claude.ai", "claude.com", "chatgpt.com", "chat.openai.com", "openai.com"}) | _LOOPBACK
_KNOWN_SCHEMES = frozenset({"cursor", "vscode", "vscode-insiders"})

_grants_cache: TtlCache[dict] = TtlCache(30.0)
_used_codes: dict[str, float] = {}


# ----- signed tokens ---------------------------------------------------------------------------------


def _key() -> bytes:
    secret = (settings.JWT_SECRET or "").encode()
    if not secret:
        raise RuntimeError("JWT_SECRET is not configured")
    return hmac.new(secret, b"vocify-mcp-oauth-v1", hashlib.sha256).digest()


def _sign(use: str, claims: dict, ttl: int) -> str:
    now = int(time.time())
    return pyjwt.encode({**claims, "use": use, "iat": now, "exp": now + ttl}, _key(), algorithm="HS256")


def _read(use: str, token: str, **checks: Any) -> Optional[dict]:
    """The claims of a token this server signed for this use and that has not expired; None otherwise."""
    try:
        claims = pyjwt.decode(
            token, _key(), algorithms=["HS256"], options={"require": ["exp", "iat", "use"]}, leeway=5, **checks
        )
    except Exception:  # noqa: BLE001 - any unreadable, forged or expired token is simply not valid
        return None
    return claims if claims.get("use") == use else None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _host(uri: str) -> str:
    parsed = urlparse(uri)
    return (parsed.hostname or parsed.scheme or "").lower()


def grant_key(client_name: str, redirect_uri: str) -> str:
    """One entry per app, not per registration: Claude registers a new client every time it connects."""
    return _digest(f"{client_name.strip().casefold()}|{_host(redirect_uri)}")[:16]


def is_known_app(redirect_uri: str) -> bool:
    parsed = urlparse(redirect_uri)
    return parsed.scheme in _KNOWN_SCHEMES or (parsed.scheme in ("https", "http") and (parsed.hostname or "").lower() in _KNOWN_HOSTS)


# ----- grants: the one stored thing ------------------------------------------------------------------


def _read_grants(supabase: Any, user_id: str, *, fresh: bool = False) -> dict:
    if not fresh:
        hit = _grants_cache.get(user_id)
        if hit is not None:
            return hit
    rows = supabase.table("user_profiles").select("oauth_grants").eq("id", user_id).limit(1).execute().data or []
    grants = rows[0].get("oauth_grants") if rows else None
    grants = grants if isinstance(grants, dict) else {}
    _grants_cache.put(user_id, grants)
    return grants


def _write_grants(supabase: Any, user_id: str, grants: dict) -> None:
    updated = supabase.table("user_profiles").update({"oauth_grants": grants}).eq("id", user_id).execute().data or []
    if not updated:
        supabase.table("user_profiles").insert({"id": user_id, "oauth_grants": grants}).execute()
    _grants_cache.put(user_id, grants)


def list_grants(supabase: Any, user_id: str) -> list[dict]:
    try:
        grants = _read_grants(supabase, user_id, fresh=True)
    except Exception:  # noqa: BLE001 - migration 080 not applied yet: nothing is connected
        logger.warning("oauth grants unreadable", exc_info=True)
        return []
    items = [
        {"client": {"client_id": key, "client_name": g.get("name"), "client_uri": g.get("host")}, "granted_at": g.get("at")}
        for key, g in grants.items()
        if isinstance(g, dict)
    ]
    return sorted(items, key=lambda item: str(item["granted_at"] or ""), reverse=True)


def revoke_grant(supabase: Any, user_id: str, key: str) -> None:
    grants = dict(_read_grants(supabase, user_id, fresh=True))
    if grants.pop(key, None) is not None:
        _write_grants(supabase, user_id, grants)


# ----- access tokens, for /mcp -----------------------------------------------------------------------


def verify_access_token(supabase: Any, token: str) -> Optional[tuple[str, str]]:
    """(user_id, app name) for an access token this server issued for this MCP URL, while its connection exists."""
    claims = _read("at", token, audience=access.server_url(), issuer=access.issuer_url())
    if not claims or not claims.get("sub") or not claims.get("gk") or not claims.get("ch"):
        return None
    try:
        grant = _read_grants(supabase, str(claims["sub"])).get(claims["gk"])
    except Exception:  # noqa: BLE001 - e.g. migration 080 not applied: no OAuth token is valid yet
        logger.warning("oauth grants unreadable", exc_info=True)
        return None
    if not isinstance(grant, dict) or claims["ch"] not in (grant.get("chains") or {}):
        return None
    return str(claims["sub"]), str(grant.get("name") or "oauth")


def _issue(user_id: str, key: str, chain: str, client_id: str, jti: str) -> OAuthToken:
    access_token = _sign(
        "at", {"iss": access.issuer_url(), "aud": access.server_url(), "sub": user_id, "gk": key, "ch": chain}, ACCESS_TTL
    )
    refresh_token = _sign(
        "rt", {"sub": user_id, "gk": key, "ch": chain, "cch": _digest(client_id)[:16], "jti": jti}, REFRESH_TTL
    )
    return OAuthToken(access_token=access_token, token_type="Bearer", expires_in=ACCESS_TTL, refresh_token=refresh_token)


# ----- the provider the SDK's handlers call -----------------------------------------------------------


class _Client(OAuthClientInformationFull):
    """There is one level of access (read-only), so scopes mean nothing here. The SDK would refuse a client that
    asks for one it was not registered with (`offline_access` is a common one), which would fail the sign-in."""

    def validate_scope(self, requested_scope: Optional[str]) -> Optional[list[str]]:
        return requested_scope.split(" ") if requested_scope else None


class _AnyScope(list):
    """Same, for a refresh request that names a scope: the SDK checks each against the token's scopes."""

    def __contains__(self, item: object) -> bool:
        return True


def _client(client_id: str) -> Optional[OAuthClientInformationFull]:
    claims = _read("client", client_id)
    if not claims:
        return None
    return _Client(
        client_id=client_id,
        redirect_uris=claims["ru"],
        client_name=claims.get("name"),
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
    )


class VocifyOAuthProvider:
    """Duck-typed OAuthAuthorizationServerProvider: only what the authorize and token handlers call."""

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        return _client(client_id)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Where to send the browser: the dashboard's consent page, carrying everything /authorize validated."""
        if params.resource and params.resource.rstrip("/") != access.server_url():
            raise AuthorizeError(error="invalid_request", error_description="resource must be " + access.server_url())
        request = _sign(
            "authreq",
            {
                "cid": client.client_id,
                "cn": client.client_name or "",
                "ru": str(params.redirect_uri),
                "rue": params.redirect_uri_provided_explicitly,
                "cc": params.code_challenge,
                "st": params.state,
            },
            REQUEST_TTL,
        )
        return f"{settings.FRONTEND_URL.rstrip('/')}/oauth/consent?authorization_id={request}"

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> Optional[AuthorizationCode]:
        claims = _read("code", authorization_code)
        if not claims or claims.get("cid") != client.client_id or claims["jti"] in _used_codes:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=[],
            expires_at=float(claims["exp"]),
            client_id=claims["cid"],
            code_challenge=claims["cc"],
            redirect_uri=claims["ru"],
            redirect_uri_provided_explicitly=bool(claims["rue"]),
            subject=claims["sub"],
        )

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode) -> OAuthToken:
        claims = _read("code", authorization_code.code)
        if not claims or claims["jti"] in _used_codes:
            raise TokenError(error="invalid_grant", error_description="authorization code is not valid")
        now = time.time()
        for jti in [j for j, until in _used_codes.items() if until < now]:
            _used_codes.pop(jti, None)
        _used_codes[claims["jti"]] = float(claims["exp"]) + 5  # single use, on this instance, for as long as it lives
        user_id, key = str(claims["sub"]), str(claims["gk"])
        chain, jti = secrets.token_urlsafe(8), secrets.token_urlsafe(16)
        stamp = datetime.now(timezone.utc).isoformat()

        def save() -> None:
            from app.deps import get_supabase

            supabase = get_supabase()
            grants = dict(_read_grants(supabase, user_id, fresh=True))
            held = grants.get(key) if isinstance(grants.get(key), dict) else {}
            chains = {**(held.get("chains") or {}), chain: {"rt": jti, "at": stamp}}
            for oldest in sorted(chains, key=lambda c: str(chains[c].get("at") or ""))[: max(0, len(chains) - MAX_CONNECTIONS)]:
                chains.pop(oldest)
            grants[key] = {"name": claims.get("cn") or "AI app", "host": _host(claims["ru"]), "at": stamp, "chains": chains}
            _write_grants(supabase, user_id, grants)

        try:
            await anyio.to_thread.run_sync(save)
        except Exception as error:  # noqa: BLE001
            logger.exception("oauth grant could not be saved")
            raise TokenError(error="server_error", error_description="could not save the connection") from error
        return _issue(user_id, key, chain, client.client_id, jti)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> Optional[RefreshToken]:
        claims = _read("rt", refresh_token)
        if not claims or claims.get("cch") != _digest(client.client_id)[:16]:
            return None
        token = RefreshToken(token=refresh_token, client_id=client.client_id, scopes=[], expires_at=int(claims["exp"]), subject=claims["sub"])
        token.__dict__["scopes"] = _AnyScope()  # set past the model's validation, which would turn it back into a plain list
        return token

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        claims = _read("rt", refresh_token.token)
        if not claims:
            raise TokenError(error="invalid_grant", error_description="refresh token is not valid")
        user_id, key, chain, presented = str(claims["sub"]), str(claims["gk"]), str(claims["ch"]), str(claims["jti"])

        def rotate() -> Optional[str]:
            """The token id to put in the new refresh token, or None when this connection no longer exists."""
            from app.deps import get_supabase

            supabase = get_supabase()
            grants = dict(_read_grants(supabase, user_id, fresh=True))
            grant = grants.get(key)
            chains = dict((grant or {}).get("chains") or {}) if isinstance(grant, dict) else {}
            current = chains.get(chain)
            if not current:
                return None
            now = time.time()
            if presented == current.get("rt"):
                new = secrets.token_urlsafe(16)
                chains[chain] = {**current, "prev": presented, "until": now + REFRESH_GRACE, "rt": new}
                grants[key] = {**grant, "chains": chains}
                _write_grants(supabase, user_id, grants)
                return new
            if presented == current.get("prev") and now < float(current.get("until") or 0):
                return str(current["rt"])  # rotated a moment ago and the app has not seen it yet: same current token
            chains.pop(chain)  # an old refresh token again: it was copied. End this one connection.
            if chains:
                grants[key] = {**grant, "chains": chains}
            else:
                grants.pop(key)
            _write_grants(supabase, user_id, grants)
            return None

        try:
            jti = await anyio.to_thread.run_sync(rotate)
        except Exception as error:  # noqa: BLE001
            logger.exception("oauth refresh failed")
            raise TokenError(error="server_error", error_description="could not refresh the connection") from error
        if jti is None:
            raise TokenError(error="invalid_grant", error_description="the connection was removed; connect again")
        return _issue(user_id, key, chain, client.client_id, jti)


provider = VocifyOAuthProvider()


# ----- consent: called by the dashboard's consent page (api/mcp_access) --------------------------------


def read_request(authorization_id: str) -> Optional[dict]:
    claims = _read("authreq", authorization_id)
    if not claims:
        return None
    return {
        "authorization_id": authorization_id,
        "redirect_uri": claims["ru"],
        "client": {"client_id": grant_key(claims["cn"] or "AI app", claims["ru"]), "client_name": claims["cn"] or None},
        "known": is_known_app(claims["ru"]),
    }


def decide(authorization_id: str, user_id: str, approve: bool) -> Optional[str]:
    """Where to send the browser after the user answered, or None if the request is gone."""
    claims = _read("authreq", authorization_id)
    if not claims:
        return None
    if not approve:
        return construct_redirect_uri(claims["ru"], error="access_denied", state=claims.get("st"))
    name = claims["cn"] or "AI app"
    code = _sign(
        "code",
        {
            "sub": user_id,
            "gk": grant_key(name, claims["ru"]),
            "cn": name,
            "cid": claims["cid"],
            "ru": claims["ru"],
            "rue": claims["rue"],
            "cc": claims["cc"],
            "jti": secrets.token_urlsafe(12),
        },
        CODE_TTL,
    )
    return construct_redirect_uri(claims["ru"], code=code, state=claims.get("st"))


# ----- dynamic client registration, with no stored client ---------------------------------------------


def _redirect_problem(uri: str) -> Optional[str]:
    parsed = urlparse(uri)
    if len(uri) > 2000 or parsed.fragment or not parsed.scheme:
        return "redirect_uris must be absolute URLs without a fragment"
    if parsed.scheme in _BAD_SCHEMES:
        return f"redirect_uris may not use {parsed.scheme}:"
    if parsed.scheme == "http" and (parsed.hostname or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        return "http redirect_uris are only allowed for localhost"
    return None


def _registration_error(description: str) -> JSONResponse:
    return JSONResponse({"error": "invalid_client_metadata", "error_description": description}, status_code=400)


async def register(request: Request) -> Response:
    """RFC 7591. The client id is the signed registration itself, so nothing is stored and a reconnect is free."""
    try:
        meta = OAuthClientMetadata.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        return _registration_error(str(error)[:300])
    uris = [str(u) for u in meta.redirect_uris or []]
    if not uris or len(uris) > MAX_REDIRECT_URIS:
        return _registration_error(f"between 1 and {MAX_REDIRECT_URIS} redirect_uris are required")
    for uri in uris:
        problem = _redirect_problem(uri)
        if problem:
            return _registration_error(problem)
    if "authorization_code" not in meta.grant_types or "code" not in meta.response_types:
        return _registration_error("grant_types must include authorization_code and response_types code")
    name = (meta.client_name or "AI app").strip()[:100] or "AI app"
    client_id = _sign("client", {"ru": uris, "name": name}, CLIENT_TTL)
    return JSONResponse(
        {
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": name,
            "redirect_uris": uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
        status_code=201,
    )


# ----- routes ------------------------------------------------------------------------------------------


def metadata() -> OAuthMetadata:
    issuer = access.issuer_url()
    return OAuthMetadata(
        issuer=issuer,
        authorization_endpoint=f"{issuer}/oauth/authorize",
        token_endpoint=f"{issuer}/oauth/token",
        registration_endpoint=f"{issuer}/oauth/register",
        response_types_supported=["code"],
        grant_types_supported=["authorization_code", "refresh_token"],
        token_endpoint_auth_methods_supported=["none"],
        code_challenge_methods_supported=["S256"],
    )


def _cors(app: Any, methods: list[str]) -> Any:
    return CORSMiddleware(app=app, allow_origins="*", allow_methods=methods, allow_headers=["MCP-Protocol-Version"])


def routes() -> list[Route]:
    """Added to the API app next to /mcp (main.py). Browsers only redirect to /oauth/authorize, so no CORS there."""
    token_handler = TokenHandler(provider, ClientAuthenticator(provider))
    return [
        Route(
            "/.well-known/oauth-authorization-server",
            endpoint=_cors(request_response(MetadataHandler(metadata()).handle), ["GET", "OPTIONS"]),
            methods=["GET", "OPTIONS"],
        ),
        Route("/oauth/authorize", endpoint=AuthorizationHandler(provider).handle, methods=["GET", "POST"]),
        Route("/oauth/token", endpoint=_cors(request_response(token_handler.handle), ["POST", "OPTIONS"]), methods=["POST", "OPTIONS"]),
        Route("/oauth/register", endpoint=_cors(request_response(register), ["POST", "OPTIONS"]), methods=["POST", "OPTIONS"]),
    ]
