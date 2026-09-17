from datetime import datetime, timedelta, timezone

import pytest

from app.services.pipedrive.client import PipedriveClient


class _FakeSupabase:
    def __init__(self):
        self.updates = []

    def table(self, name):
        assert name == "crm_connections"
        return self

    def update(self, row):
        self.updates.append(row)
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        return type("R", (), {"data": None})()


@pytest.mark.asyncio
async def test_persist_tokens_uses_response_expires_in(monkeypatch):
    supabase = _FakeSupabase()
    client = PipedriveClient(
        "https://acme.pipedrive.com",
        "old",
        refresh_token="ref",
        connection_id="c1",
        supabase=supabase,
    )

    async def fake_refresh(_token):
        return {
            "access_token": "new",
            "refresh_token": "ref2",
            "expires_in": 7200,
            "api_domain": "https://acme.pipedrive.com",
        }

    monkeypatch.setattr("app.services.pipedrive.client.refresh_tokens", fake_refresh)
    await client._do_refresh()
    assert client.access_token == "new"
    assert supabase.updates
    expires = datetime.fromisoformat(supabase.updates[0]["token_expires_at"].replace("Z", "+00:00"))
    delta = expires - datetime.now(timezone.utc)
    assert timedelta(minutes=110) < delta < timedelta(minutes=130)
