"""Lista 3: Pipedrive deals/persons/activities are owned by the acting Vocify user's own
Pipedrive user (matched by login email), not by whoever connected Pipedrive - mirrors
HubSpot's _get_hubspot_owner_id_for_user (see tests/test_hubspot_owner_cache.py)."""

from uuid import uuid4

import pytest

from app.models.memo import MemoExtraction
from app.services.pipedrive.sync import (
    PipedriveSyncService,
    _get_pipedrive_owner_id_for_user,
    owner_id_from_connection_metadata,
    with_cached_owner_id,
)


def test_per_user_owner_cache_hit():
    meta = {"pipedrive_owners": {"user-1": "111", "user-2": "222"}}
    assert owner_id_from_connection_metadata(meta, "user-1") == "111"
    assert owner_id_from_connection_metadata(meta, "user-3") is None


def test_with_cached_owner_id_round_trips():
    meta = with_cached_owner_id({}, "user-1", "111")
    assert meta["pipedrive_owners"]["user-1"] == "111"
    assert owner_id_from_connection_metadata(meta, "user-1") == "111"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self._store = store
        self._table = table
        self._filters = []
        self._mode = "select"
        self._payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def single(self):
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        if self._mode == "update":
            for row in rows:
                if all(row.get(c) == v for c, v in self._filters):
                    row.update(self._payload)
            return _Result(None)
        filtered = [r for r in rows if all(r.get(c) == v for c, v in self._filters)]
        return _Result(filtered[0] if filtered else None)


class _AuthAdminUser:
    def __init__(self, email):
        self.user = type("U", (), {"email": email})()


class _Auth:
    def __init__(self, email):
        self._email = email

    class _Admin:
        def __init__(self, email):
            self._email = email

        def get_user_by_id(self, _user_id):
            return _AuthAdminUser(self._email)

    @property
    def admin(self):
        return self._Admin(self._email)


class _FakeSupabase:
    def __init__(self, *, email, connection_row=None):
        self.tables: dict[str, list] = {"crm_connections": [connection_row] if connection_row else []}
        self.auth = _Auth(email)

    def table(self, name):
        return _Query(self.tables, name)


class _OwnerClient:
    def __init__(self, users):
        self._users = users
        self.gets = []
        self.posts = []
        self.patches = []
        self.connection_id = "c1"
        self.api_domain = "https://acme.pipedrive.com"

    async def get(self, path, *, version="v2", params=None):
        self.gets.append((path, version, params))
        if path == "/users/find":
            term = (params or {}).get("term", "").lower()
            return {"data": [u for u in self._users if u["email"].lower() == term]}
        if path == "/activityTypes":
            return {"data": [{"key_string": "task", "icon_key": "task"}]}
        if path == "/organizations/search":
            return {"data": {"items": []}}
        if path == "/persons/search":
            return {"data": {"items": []}}
        if path.startswith("/deals/"):
            return {"data": {"id": 1, "title": "Acme"}}
        return {"data": []}

    async def post(self, path, json_body=None, *, version="v2"):
        self.posts.append((path, json_body, version))
        if path == "/organizations":
            return {"data": {"id": 10, "name": json_body["name"]}}
        if path == "/persons":
            return {"data": {"id": 20, "name": json_body["name"]}}
        if path == "/deals":
            return {"data": {"id": 30, "title": json_body.get("title")}}
        if path == "/notes":
            return {"data": {"id": 40}}
        if path == "/activities":
            return {"data": {"id": 50}}
        return {"data": {"id": 99}}

    async def patch(self, path, json_body, *, version="v2"):
        self.patches.append((path, json_body))
        return {"data": {"id": 30}}


class _Updates:
    async def create_update(self, **_k):
        return "u1"


@pytest.mark.asyncio
async def test_resolves_owner_by_matching_login_email_to_a_pipedrive_user():
    supabase = _FakeSupabase(
        email="ana@acme.com",
        connection_row={"id": "c1", "metadata": {}},
    )
    client = _OwnerClient(users=[{"id": 77, "email": "ana@acme.com"}])
    owner_id = await _get_pipedrive_owner_id_for_user(client, supabase, "user-1", "c1")
    assert owner_id == "77"
    assert client.gets[0][0] == "/users/find"
    assert client.gets[0][1] == "v1"
    assert client.gets[0][2] == {"term": "ana@acme.com", "search_by_email": 1}
    # Cached for next time.
    cached_meta = supabase.tables["crm_connections"][0]["metadata"]
    assert cached_meta["pipedrive_owners"]["user-1"] == "77"


@pytest.mark.asyncio
async def test_second_call_uses_the_cache_and_skips_the_api():
    supabase = _FakeSupabase(
        email="ana@acme.com",
        connection_row={"id": "c1", "metadata": {"pipedrive_owners": {"user-1": "77"}}},
    )
    client = _OwnerClient(users=[{"id": 77, "email": "ana@acme.com"}])
    owner_id = await _get_pipedrive_owner_id_for_user(client, supabase, "user-1", "c1")
    assert owner_id == "77"
    assert client.gets == []


@pytest.mark.asyncio
async def test_no_match_returns_none():
    supabase = _FakeSupabase(email="ana@acme.com", connection_row={"id": "c1", "metadata": {}})
    client = _OwnerClient(users=[{"id": 5, "email": "someone-else@acme.com"}])
    assert await _get_pipedrive_owner_id_for_user(client, supabase, "user-1", "c1") is None


@pytest.mark.asyncio
async def test_no_supabase_returns_none():
    client = _OwnerClient(users=[{"id": 77, "email": "ana@acme.com"}])
    assert await _get_pipedrive_owner_id_for_user(client, None, "user-1", "c1") is None


@pytest.mark.asyncio
async def test_created_deal_and_person_are_stamped_with_the_resolved_owner():
    supabase = _FakeSupabase(email="ana@acme.com", connection_row={"id": "c1", "metadata": {}})
    client = _OwnerClient(users=[{"id": 77, "email": "ana@acme.com"}])
    svc = PipedriveSyncService(client, supabase, _Updates())
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="user-1",
        connection_id="c1",
        extraction=MemoExtraction(contactName="Ada", companyName="Acme", summary="Hi"),
        is_new_deal=True,
        default_stage_id="5",
        auto_create_companies=True,
        auto_create_contacts=True,
        create_note=False,
    )
    assert result.success, result.error
    deal_post = next(p for p in client.posts if p[0] == "/deals")
    assert deal_post[1]["owner_id"] == 77
    person_post = next(p for p in client.posts if p[0] == "/persons")
    assert person_post[1]["owner_id"] == 77


@pytest.mark.asyncio
async def test_activity_is_stamped_with_the_resolved_owner():
    supabase = _FakeSupabase(email="ana@acme.com", connection_row={"id": "c1", "metadata": {}})
    client = _OwnerClient(users=[{"id": 77, "email": "ana@acme.com"}])
    svc = PipedriveSyncService(client, supabase, _Updates())
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="user-1",
        connection_id="c1",
        extraction=MemoExtraction(companyName="Acme", nextSteps=["Send proposal"]),
        is_new_deal=True,
        default_stage_id="5",
        auto_create_companies=True,
        create_note=False,
    )
    assert result.success, result.error
    activity_post = next(p for p in client.posts if p[0] == "/activities")
    assert activity_post[1]["owner_id"] == 77


@pytest.mark.asyncio
async def test_owner_is_never_stamped_on_a_plain_update_of_an_existing_deal():
    """Lista 3: owner is set only on create; an existing deal's owner is never touched
    by a plain sync (only the handoff path reassigns it)."""
    supabase = _FakeSupabase(email="ana@acme.com", connection_row={"id": "c1", "metadata": {}})
    client = _OwnerClient(users=[{"id": 77, "email": "ana@acme.com"}])
    svc = PipedriveSyncService(client, supabase, _Updates())
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="user-1",
        connection_id="c1",
        extraction=MemoExtraction(companyName="Acme", dealAmount=500),
        deal_id="30",
        is_new_deal=False,
        allowed_fields=["value"],
        create_note=False,
    )
    assert result.success, result.error
    assert client.patches, "expected an update patch"
    for _path, body in client.patches:
        assert "owner_id" not in body
    assert not any(p[0] == "/persons" for p in client.posts)


@pytest.mark.asyncio
async def test_owner_is_never_stamped_on_a_matched_existing_person():
    """A person found by email search is reused as-is - owner is a create-only stamp."""
    supabase = _FakeSupabase(email="ana@acme.com", connection_row={"id": "c1", "metadata": {}})
    client = _OwnerClient(users=[{"id": 77, "email": "ana@acme.com"}])

    async def search_persons(_term, *, fields, limit):
        return [{"id": 20, "emails": [{"value": "existing@acme.com", "primary": True}]}]

    svc = PipedriveSyncService(client, supabase, _Updates())
    svc.search.search_persons = search_persons
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="user-1",
        connection_id="c1",
        extraction=MemoExtraction(
            contactName="Ada", contactEmail="existing@acme.com", companyName="Acme", summary="Hi"
        ),
        skip_deal=True,
        auto_create_contacts=True,
        create_note=False,
    )
    assert result.success, result.error
    assert not any(p[0] == "/persons" for p in client.posts)
