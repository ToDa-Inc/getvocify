"""GET/PUT /crm/call-recordings-preference: the rep's own switch for their dialer's CRM recordings."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import crm as crm_api
from app.deps import get_supabase, get_user_id


class _Profiles:
    def __init__(self):
        self.value = None
        self.writes = []

    def table(self, name):
        assert name == "user_profiles"
        db = self
        chain = type("Chain", (), {})()

        def update(payload):
            db.writes.append(payload)
            db.value = payload["process_crm_call_recordings"]
            return chain

        chain.select = chain.eq = chain.limit = lambda *_a, **_k: chain
        chain.update = update
        chain.execute = lambda: type("R", (), {"data": [] if db.value is None else [{"process_crm_call_recordings": db.value}]})()
        return chain


def _client(db):
    app = FastAPI()
    app.include_router(crm_api.router)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_user_id] = lambda: "rep-1"
    return TestClient(app)


def test_a_rep_who_never_chose_has_recordings_left_alone():
    assert _client(_Profiles()).get("/api/v1/crm/call-recordings-preference").json() == {"process": False}


def test_turning_it_on_is_saved_and_read_back():
    db = _Profiles()
    client = _client(db)
    assert client.put("/api/v1/crm/call-recordings-preference", json={"process": True}).json() == {"process": True}
    assert db.writes == [{"process_crm_call_recordings": True}]
    assert client.get("/api/v1/crm/call-recordings-preference").json() == {"process": True}
