"""The DB client reuses one bounded connection pool and stays on the service key."""

import pytest

from app import deps


@pytest.fixture
def fresh_client(monkeypatch):
    monkeypatch.setattr(deps.settings, "SUPABASE_URL", "https://abcdefghijklmnopqrst.supabase.co")
    monkeypatch.setattr(deps.settings, "SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setattr(deps, "_supabase_client", None)
    yield
    deps._supabase_client = None


def test_every_call_shares_one_pool(fresh_client):
    first = deps.get_supabase()
    session = first.postgrest.session
    for _ in range(5):
        assert deps.get_supabase().postgrest.session is session
    assert first.storage.session is session


def test_queries_are_bounded(fresh_client):
    timeout = deps.get_supabase().postgrest.session.timeout
    assert timeout.connect == 5.0
    assert timeout.read == 30.0
    assert timeout.pool == 10.0


def test_user_token_is_swapped_back_to_the_service_key(fresh_client):
    client = deps.get_supabase()
    client.postgrest  # built with the service key
    client.options.headers["Authorization"] = "Bearer user-jwt"  # what a SIGNED_IN event does
    client._postgrest = None

    client = deps.get_supabase()

    assert client.options.headers["Authorization"] == "Bearer service-key"
    assert client.postgrest.headers["Authorization"] == "Bearer service-key"
