"""A Vocify-placed call, logged in Pipedrive as a done call activity."""

import pytest

from app.api import crm_pipedrive
from app.services.pipedrive import call_log, sync
from app.services.telephony import call_processor

CONNECTION = {"id": "conn-1", "status": "connected"}
ROW = {
    "carrier_call_id": "CA1",
    "user_id": "rep-1",
    "to_number": "+34 611 222 333",
    "hubspot_contact_id": "42",
    "hubspot_deal_id": "7",
    "answered_at": "2026-10-30T10:00:00+00:00",
    "provider_state": {},
}


class FakeClient:
    def __init__(self, *, search_hits=None, fail_duration=False):
        self.posts = []
        self.search_hits = search_hits or []
        self.fail_duration = fail_duration

    async def get(self, path, *, version="v2", params=None):
        if path == "/activityTypes":
            return {"data": [{"key_string": "meeting"}, {"key_string": "call", "icon_key": "call"}]}
        if path == "/persons/42":
            return {"data": {"id": 42, "name": "Ana Pérez"}}
        if path == "/persons/search":
            return {"data": {"items": [{"item": hit} for hit in self.search_hits]}}
        raise AssertionError(f"unexpected GET {path}")

    async def post(self, path, json_body=None, *, version="v2"):
        self.posts.append((path, json_body))
        if self.fail_duration and "duration" in json_body:
            raise RuntimeError("400 bad duration")
        return {"data": {"id": 901}}


class FakeTable:
    def __init__(self, db):
        self.db = db

    def update(self, values):
        self.db.updates.append(values)
        return self

    def eq(self, *_):
        return self

    def execute(self):
        return self


class FakeDb:
    def __init__(self):
        self.updates = []

    def table(self, _name):
        return FakeTable(self)


@pytest.fixture
def world(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(crm_pipedrive, "_pd_client_from_row", lambda _row, _sb: client)

    async def owner(*_args, **_kwargs):
        return "5"

    monkeypatch.setattr(sync, "_get_pipedrive_owner_id_for_user", owner)
    return client, FakeDb()


@pytest.mark.asyncio
async def test_answered_call_is_a_done_call_with_its_duration_on_person_and_deal(world):
    client, db = world
    activity = await call_log.log_call(db, CONNECTION, ROW, duration=125, disposition="connected")
    assert activity == "901"
    path, body = client.posts[0]
    assert path == "/activities"
    assert body == {
        "subject": "Llamada con Ana Pérez",
        "type": "call",
        "done": True,
        "due_date": "2026-10-30",
        "due_time": "10:02",
        "note": "Llamada realizada con Vocify.",
        "person_id": 42,
        "deal_id": 7,
        "owner_id": 5,
        "duration": "00:02:05",
    }
    assert db.updates == [{"status": "logged", "provider_state": {"pipedrive_activity_id": "901"}}]


@pytest.mark.asyncio
async def test_unanswered_call_says_so_and_has_no_duration(world):
    client, db = world
    await call_log.log_call(db, CONNECTION, ROW, duration=0, disposition="no_answer")
    _, body = client.posts[0]
    assert body["note"] == "Sin respuesta." and "duration" not in body and body["done"] is True


@pytest.mark.asyncio
async def test_a_duration_pipedrive_refuses_does_not_lose_the_call(world):
    client, db = world
    client.fail_duration = True
    assert await call_log.log_call(db, CONNECTION, ROW, duration=60, disposition="connected") == "901"
    assert "duration" not in client.posts[-1][1]


@pytest.mark.asyncio
async def test_without_a_contact_the_person_is_the_one_with_the_dialed_number(world):
    client, db = world
    client.search_hits = [{"id": 42, "phones": ["+34611222333"]}, {"id": 43, "phones": ["+34600000000"]}]
    row = {**ROW, "hubspot_contact_id": None}
    await call_log.log_call(db, CONNECTION, row, duration=30, disposition="connected")
    assert client.posts[0][1]["person_id"] == 42


@pytest.mark.asyncio
async def test_two_people_with_the_number_log_nothing_rather_than_guess(world):
    client, db = world
    client.search_hits = [{"id": 42, "phones": ["+34611222333"]}, {"id": 43, "phones": [{"value": "611 222 333"}]}]
    row = {**ROW, "hubspot_contact_id": None}
    assert await call_log.log_call(db, CONNECTION, row, duration=30, disposition="connected") is None
    assert client.posts == [] and db.updates == []


@pytest.mark.asyncio
async def test_a_pipedrive_failure_never_raises(monkeypatch, world):
    client, db = world

    async def boom(*_a, **_k):
        raise RuntimeError("down")

    monkeypatch.setattr(client, "post", boom)
    assert await call_log.log_call(db, CONNECTION, ROW, duration=30, disposition="connected") is None


def test_a_logged_call_is_not_logged_twice():
    assert call_log.already_logged({"provider_state": {"pipedrive_activity_id": "901"}}) is True
    assert call_log.already_logged({"provider_state": None}) is False


@pytest.mark.asyncio
async def test_hubspot_companies_keep_their_path(monkeypatch):
    monkeypatch.setattr(call_log, "get_crm_connection", lambda _sb, _u, provider: {"id": "h"} if provider == "hubspot" else None)
    assert await call_processor._log_in_pipedrive(object(), ROW, 10, "connected") is False


@pytest.mark.asyncio
async def test_pipedrive_only_companies_log_in_pipedrive_once(monkeypatch):
    monkeypatch.setattr(
        call_log, "get_crm_connection", lambda _sb, _u, provider: CONNECTION if provider == "pipedrive" else None
    )
    logged = []

    async def log_call(*args, **kwargs):
        logged.append(kwargs["disposition"])

    monkeypatch.setattr(call_log, "log_call", log_call)
    assert await call_processor._log_in_pipedrive(object(), ROW, 10, "connected") is True
    assert await call_processor._log_in_pipedrive(
        object(), {**ROW, "provider_state": {"pipedrive_activity_id": "901"}}, 10, "connected"
    ) is True
    assert logged == ["connected"]
