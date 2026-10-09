"""T4/D8: the AE reads the SDR's memos of a contact handed off to them - detail (get_memo)
and list (scope=handoffs) - never another SDR's, another contact's, or the reverse (SDR
reading the AE). Approve/preview never grant a handoff read (T4 review, BLOCKING #1)."""

import os
from uuid import UUID

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-memo-handoff-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-memo-handoff-32")

import pytest
from fastapi import HTTPException

from app.api import memos as api
from app.services import feature_flags
from app.services.company import Membership

COMPANY = "co-1"
MEMO_ID = "00000000-0000-0000-0000-000000000001"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self.store = store
        self.table_name = table
        self.filters = []
        self.order_key = None
        self.desc = False
        self.cap = None
        self.skip = 0

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, set(values)))
        return self

    def order(self, column, desc=False):
        self.order_key, self.desc = column, desc
        return self

    def limit(self, count):
        self.cap = count
        return self

    def offset(self, count):
        self.skip = count
        return self

    def execute(self):
        if self.table_name in self.store.broken:
            raise RuntimeError(f"{self.table_name} unavailable")
        rows = list(self.store.tables.get(self.table_name, []))
        for op, column, value in self.filters:
            if op == "eq":
                rows = [r for r in rows if r.get(column) == value]
            elif op == "in":
                rows = [r for r in rows if r.get(column) in value]
        if self.order_key:
            rows.sort(key=lambda r: str(r.get(self.order_key) or ""), reverse=self.desc)
        if self.skip:
            rows = rows[self.skip:]
        if self.cap is not None:
            rows = rows[: self.cap]
        return _Result(rows)


class _Store:
    def __init__(self, **tables):
        self.tables = tables
        self.broken = set()

    def table(self, name):
        return _Query(self, name)


MEMBERS = [
    {"user_id": "sdr-1", "role": "member", "status": "active", "email": "s@co.es", "full_name": "Sara"},
    {"user_id": "sdr-2", "role": "member", "status": "active", "email": "s2@co.es", "full_name": "Sonia"},
    {"user_id": "ae-1", "role": "member", "status": "active", "email": "a@co.es", "full_name": "Alex"},
]


def _memo(memo_id, user_id, *, contact="c-1"):
    return {
        "id": memo_id,
        "user_id": user_id,
        "audio_url": "",
        "audio_duration": 60,
        "status": "approved",
        "created_at": "2026-09-22T10:00:00+00:00",
        "hubspot_contact_id": contact,
    }


def _patch_viewer(monkeypatch, *, role_by_user):
    def fake_scope(_supabase, viewer_id):
        if viewer_id not in role_by_user:
            return None, [], {}
        membership = Membership(
            id="m", company_id=COMPANY, user_id=viewer_id, role=role_by_user[viewer_id], status="active",
        )
        from app.services.activity_scope import authors_by_user_id

        return membership, MEMBERS, authors_by_user_id(MEMBERS)

    monkeypatch.setattr(api, "load_viewer_scope", fake_scope)


@pytest.fixture(autouse=True)
def _clear_flags():
    feature_flags.clear_cache()
    yield
    feature_flags.clear_cache()


M1 = "00000000-0000-0000-0000-0000000000a1"
M2 = "00000000-0000-0000-0000-0000000000a2"


def _store(*, handoff_status="active", flag_on=True):
    return _Store(
        memos=[_memo(M1, "sdr-1", contact="c-1"), _memo(M2, "sdr-2", contact="c-2")],
        deal_handoffs=[
            {
                "company_id": COMPANY,
                "contact_id": "c-1",
                "sdr_user_id": "sdr-1",
                "ae_user_id": "ae-1",
                "status": handoff_status,
            }
        ],
        company_feature_flags=(
            [{"company_id": COMPANY, "flag": "HANDOFF_ENABLED", "enabled": True}] if flag_on else []
        ),
    )


async def test_ae_reads_the_handed_off_sdr_memo(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"ae-1": "member"})
    memo = api.get_memo(UUID(M1), supabase=_store(), user_id="ae-1")
    assert memo.userId == "sdr-1"


async def test_ae_cannot_read_a_different_sdr_memo(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"ae-1": "member"})
    store = _store()
    store.tables["memos"] = [_memo(MEMO_ID, "sdr-2", contact="c-2")]
    with pytest.raises(HTTPException) as exc:
        api.get_memo(UUID(MEMO_ID), supabase=store, user_id="ae-1")
    assert exc.value.status_code == 404


async def test_sdr_cannot_read_the_ae(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"sdr-1": "member"})
    store = _store()
    store.tables["memos"] = [_memo(MEMO_ID, "ae-1", contact="c-1")]
    with pytest.raises(HTTPException) as exc:
        api.get_memo(UUID(MEMO_ID), supabase=store, user_id="sdr-1")
    assert exc.value.status_code == 404


async def test_flag_off_denies_the_handoff_read(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"ae-1": "member"})
    store = _store(flag_on=False)
    store.tables["memos"] = [_memo(MEMO_ID, "sdr-1", contact="c-1")]
    with pytest.raises(HTTPException) as exc:
        api.get_memo(UUID(MEMO_ID), supabase=store, user_id="ae-1")
    assert exc.value.status_code == 404


async def test_closed_handoff_still_readable(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"ae-1": "member"})
    store = _store(handoff_status="closed")
    store.tables["memos"] = [_memo(MEMO_ID, "sdr-1", contact="c-1")]
    memo = api.get_memo(UUID(MEMO_ID), supabase=store, user_id="ae-1")
    assert memo.userId == "sdr-1"


async def test_list_scope_handoffs_returns_the_sdr_memo_for_that_contact(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"ae-1": "member"})
    store = _store()
    result = await api.list_memos(
        supabase=store, user_id="ae-1", scope="handoffs", hubspot_contact_id="c-1",
    )
    assert [str(m.id) for m in result] == [M1]


async def test_list_scope_handoffs_without_contact_id_is_empty(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"ae-1": "member"})
    result = await api.list_memos(supabase=_store(), user_id="ae-1", scope="handoffs")
    assert result == []


async def test_list_scope_handoffs_wrong_contact_is_empty(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"ae-1": "member"})
    result = await api.list_memos(
        supabase=_store(), user_id="ae-1", scope="handoffs", hubspot_contact_id="c-2",
    )
    assert result == []


async def test_list_scope_handoffs_pools_multiple_sdrs_for_the_same_contact(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"ae-1": "member"})
    store = _store()
    store.tables["deal_handoffs"].append(
        {"company_id": COMPANY, "contact_id": "c-1", "sdr_user_id": "sdr-2", "ae_user_id": "ae-1", "status": "closed"}
    )
    store.tables["memos"] = [_memo(M1, "sdr-1", contact="c-1"), _memo(M2, "sdr-2", contact="c-1")]
    result = await api.list_memos(
        supabase=store, user_id="ae-1", scope="handoffs", hubspot_contact_id="c-1",
    )
    assert {str(m.id) for m in result} == {M1, M2}


async def test_list_scope_handoffs_excludes_an_sdr_no_longer_in_the_company(monkeypatch):
    def fake_scope(_supabase, viewer_id):
        if viewer_id != "ae-1":
            return None, [], {}
        members = [
            {"user_id": "sdr-1", "role": "member", "status": "removed", "email": "s@co.es", "full_name": "Sara"},
            {"user_id": "ae-1", "role": "member", "status": "active", "email": "a@co.es", "full_name": "Alex"},
        ]
        from app.services.activity_scope import authors_by_user_id
        membership = Membership(id="m", company_id=COMPANY, user_id="ae-1", role="member", status="active")
        return membership, members, authors_by_user_id(members)

    monkeypatch.setattr(api, "load_viewer_scope", fake_scope)
    result = await api.list_memos(
        supabase=_store(), user_id="ae-1", scope="handoffs", hubspot_contact_id="c-1",
    )
    assert result == []


# --- BLOCKING review fix: approve/preview never grant a handoff read (T4 review) ---

async def test_ae_gets_404_approving_the_sdr_memo(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"ae-1": "member"})
    store = _store()
    store.tables["memos"] = [_memo(M1, "sdr-1", contact="c-1")]
    with pytest.raises(HTTPException) as exc:
        await api.approve_memo(UUID(M1), None, supabase=store, user_id="ae-1")
    assert exc.value.status_code == 404


async def test_ae_gets_404_get_preview_of_the_sdr_memo(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"ae-1": "member"})
    store = _store()
    store.tables["memos"] = [_memo(M1, "sdr-1", contact="c-1")]
    with pytest.raises(HTTPException) as exc:
        await api.get_approval_preview(UUID(M1), supabase=store, user_id="ae-1")
    assert exc.value.status_code == 404


async def test_ae_gets_404_post_preview_of_the_sdr_memo(monkeypatch):
    _patch_viewer(monkeypatch, role_by_user={"ae-1": "member"})
    store = _store()
    store.tables["memos"] = [_memo(M1, "sdr-1", contact="c-1")]
    with pytest.raises(HTTPException) as exc:
        await api.post_approval_preview(UUID(M1), None, supabase=store, user_id="ae-1")
    assert exc.value.status_code == 404
