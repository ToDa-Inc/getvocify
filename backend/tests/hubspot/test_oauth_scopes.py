"""The OAuth URL may only ask for scopes the HubSpot app declares, or consent fails for everyone."""

import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-oauth-32bytes")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-oauth-32bytes")

from app.services.hubspot import oauth

APP_CONFIG = Path(__file__).resolve().parents[3] / "hubspot-app" / "src" / "app" / "app-hsmeta.json"


def _app_auth() -> dict:
    return json.loads(APP_CONFIG.read_text(encoding="utf-8"))["config"]["auth"]


def _authorize_params(monkeypatch) -> dict[str, list[str]]:
    monkeypatch.setattr(oauth.settings, "HUBSPOT_CLIENT_ID", "client")
    monkeypatch.setattr(oauth.settings, "HUBSPOT_CLIENT_SECRET", "secret")
    monkeypatch.setattr(oauth.settings, "HUBSPOT_REDIRECT_URI", "https://api.example.com/callback")
    monkeypatch.setattr(oauth.settings, "JWT_SECRET", "test-jwt-secret-for-oauth-32bytes")
    return parse_qs(urlsplit(oauth.build_authorize_url("user-1")).query)


def test_required_and_optional_scopes_match_the_app_config():
    auth = _app_auth()
    assert sorted(oauth.HUBSPOT_OAUTH_SCOPES) == sorted(auth["requiredScopes"])
    assert sorted(oauth.HUBSPOT_OPTIONAL_SCOPES) == sorted(auth["optionalScopes"])


def test_email_read_is_optional_so_existing_installs_keep_working(monkeypatch):
    params = _authorize_params(monkeypatch)
    assert "sales-email-read" not in params["scope"][0].split()
    assert params["optional_scope"][0].split() == ["sales-email-read"]
