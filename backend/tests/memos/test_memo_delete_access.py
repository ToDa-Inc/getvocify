"""DELETE /memos/{id}: the recorder can; so can an owner or admin of the same company; a plain member
(even one who reads the team's activity) and anyone from another company get the 404 of a missing memo."""

import asyncio
import os
from uuid import UUID

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-memo-delete-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-memo-delete-32")

import pytest
from fastapi import HTTPException

from app.api import memos as api
from app.services.activity_scope import authors_by_user_id
from app.services.company import Membership

MEMO_ID = "00000000-0000-0000-0000-0000000000d1"
MEMBERS = [
    {"user_id": "rep", "role": "member", "status": "active", "email": "r@co.es", "full_name": "Rep"},
    {"user_id": "peer", "role": "member", "status": "active", "email": "p@co.es", "full_name": "Peer"},
    {"user_id": "boss", "role": "owner", "status": "active", "email": "b@co.es", "full_name": "Boss"},
]


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, op):
        self.store, self.op, self.filters = store, op, []

    def select(self, *_a, **_k):
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        rows = [r for r in self.store.memos if all(str(r.get(c)) == str(v) for c, v in self.filters)]
        if self.op == "delete":
            self.store.memos = [r for r in self.store.memos if r not in rows]
        return _Result(rows)


class _Store:
    def __init__(self):
        self.memos = [{"id": MEMO_ID, "user_id": "rep", "audio_url": ""}]

    def table(self, name):
        assert name == "memos"
        return _Query(self, "select")


def _viewer(monkeypatch, role_by_user, visibility=None):
    def fake_scope(_supabase, viewer_id):
        if viewer_id not in role_by_user:
            return None, [], {}
        membership = Membership(id="m", company_id="co", user_id=viewer_id, role=role_by_user[viewer_id], status="active", visibility=visibility or "own")
        return membership, MEMBERS, authors_by_user_id(MEMBERS)

    monkeypatch.setattr(api, "load_viewer_scope", fake_scope)


def _delete(store, user_id):
    return asyncio.run(api.delete_memo(UUID(MEMO_ID), supabase=store, user_id=user_id))


def test_the_recorder_deletes_their_own_memo(monkeypatch):
    _viewer(monkeypatch, {"rep": "member"})
    store = _Store()
    assert _delete(store, "rep")["success"] is True
    assert store.memos == []


def test_an_owner_deletes_a_teammates_memo(monkeypatch):
    _viewer(monkeypatch, {"boss": "owner"})
    store = _Store()
    assert _delete(store, "boss")["success"] is True
    assert store.memos == []


@pytest.mark.parametrize("viewer", ["peer", "stranger"])
def test_a_peer_or_a_stranger_gets_a_404_and_the_memo_stays(monkeypatch, viewer):
    _viewer(monkeypatch, {"peer": "member"})
    store = _Store()
    with pytest.raises(HTTPException) as caught:
        _delete(store, viewer)
    assert caught.value.status_code == 404
    assert len(store.memos) == 1


def test_a_member_who_sees_the_team_still_cannot_delete(monkeypatch):
    _viewer(monkeypatch, {"peer": "member"}, visibility="team")
    store = _Store()
    with pytest.raises(HTTPException) as caught:
        _delete(store, "peer")
    assert caught.value.status_code == 404
    assert len(store.memos) == 1
