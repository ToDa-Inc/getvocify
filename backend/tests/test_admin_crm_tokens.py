"""The admin console shows a CRM connection's state, never the provider's tokens."""

import asyncio
import json
import os
import re
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-admin-crm")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-admin-crm")

from app.api import admin

USER_ID = uuid4()
COMPANY_ID = uuid4()
ACCESS = "pat-na1-ACCESS-secret-value"
REFRESH = "REFRESH-secret-value"
CONNECTION = {
    "id": "conn-1",
    "user_id": str(USER_ID),
    "company_id": str(COMPANY_ID),
    "provider": "hubspot",
    "status": "connected",
    "access_token": ACCESS,
    "refresh_token": REFRESH,
    "client_secret": "client-secret-value",
    "token_expires_at": "2026-12-01T00:00:00+00:00",
    "last_synced_at": "2026-10-01T00:00:00+00:00",
    "created_at": "2026-09-01T00:00:00+00:00",
}
ROWS = {
    "crm_connections": [CONNECTION],
    "user_profiles": [{"id": str(USER_ID), "full_name": "Ada"}],
}


class _Query:
    """Returns each row cut to the selected columns, as PostgREST does."""

    def __init__(self, table, selects):
        self._table = table
        self._selects = selects
        self._columns = None

    def select(self, columns="*", **_):
        self._columns = columns
        self._selects.append((self._table, columns))
        return self

    def __getattr__(self, _name):
        return lambda *args, **kwargs: self

    def execute(self):
        rows = ROWS.get(self._table, [])
        if self._columns and self._columns != "*":
            wanted = self._columns.split(",")
            rows = [{k: v for k, v in row.items() if k in wanted} for row in rows]
        return type("Result", (), {"data": rows, "count": len(rows)})()


class _FakeSupabase:
    def __init__(self):
        self.selects = []

    def table(self, name):
        return _Query(name, self.selects)


def _assert_no_secrets(response, supabase):
    text = json.dumps(response, default=str)
    for secret in (ACCESS, REFRESH, "client-secret-value"):
        assert secret not in text
    keys = set(re.findall(r'"([^"]+)":', text))
    leaking = {k for k in keys if re.search(r"secret|key|password|token", k) and k != "token_expires_at"}
    assert not leaking
    asked = [cols for table, cols in supabase.selects if table == "crm_connections"]
    assert asked and "*" not in asked and not any("access_token" in c or "refresh_token" in c for c in asked)


def test_company_detail_returns_no_crm_tokens():
    supabase = _FakeSupabase()
    with patch.object(admin, "_company_admin_payload", return_value={"company": {"id": str(COMPANY_ID)}}):
        response = asyncio.run(
            admin.get_company_admin(company_id=COMPANY_ID, supabase=supabase, _="test-key")
        )
    assert response["crm_connections"][0]["provider"] == "hubspot"
    _assert_no_secrets(response, supabase)


def test_account_detail_returns_no_crm_tokens():
    supabase = _FakeSupabase()
    with patch.object(admin, "_auth_user_by_id", return_value={"email": "ada@acme.com"}):
        response = asyncio.run(admin.get_account(user_id=USER_ID, supabase=supabase, _="test-key"))
    assert response["connections"][0]["provider"] == "hubspot"
    _assert_no_secrets(response, supabase)
