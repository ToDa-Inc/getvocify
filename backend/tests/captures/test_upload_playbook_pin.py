"""Every capture path pins the playbook (Lista 3 fix): uploads, extension recordings and
HubSpot-calling recordings used to insert without one, so they were never scored."""

from __future__ import annotations

from app.services import captures


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, name):
        self.store, self.name = store, name
        self.payload = None

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        self.store.inserted.append(dict(self.payload))
        return _Result([{**self.payload, "id": "memo-1"}])


class _Store:
    def __init__(self):
        self.inserted: list[dict] = []

    def table(self, name):
        return _Query(self, name)


def _stub(monkeypatch, *, fields=None, raises=False):
    seen = {}

    def fake(_supabase, company_id, **kwargs):
        if raises:
            raise RuntimeError("playbook store down")
        seen.update({"company_id": company_id, **kwargs})
        return dict(fields or {})

    monkeypatch.setattr(captures, "playbook_fields_for_capture", fake)
    monkeypatch.setattr("app.services.company.sales_role_for_user", lambda _s, _u: "sdr")
    return seen


def test_an_upload_is_pinned_to_the_reps_flow(monkeypatch):
    seen = _stub(monkeypatch, fields={"sales_motion_key": "discovery", "playbook_version_id": "v-7"})
    store = _Store()
    captures.insert_memo_row(store, {"user_id": "u1", "company_id": "co-1", "source_type": "voice_memo"}, pin_playbook=True)
    row = store.inserted[0]
    assert row["playbook_version_id"] == "v-7" and row["sales_motion_key"] == "discovery"
    assert seen["company_id"] == "co-1"
    assert seen["sales_role"] == "sdr"
    assert seen["default_when_unspecified"] is True


def test_an_existing_pin_is_kept(monkeypatch):
    _stub(monkeypatch, fields={"playbook_version_id": "other"})
    store = _Store()
    captures.insert_memo_row(
        store, {"user_id": "u1", "company_id": "co-1", "playbook_version_id": "v-1"}, pin_playbook=True,
    )
    assert store.inserted[0]["playbook_version_id"] == "v-1"


def test_a_failed_pin_never_blocks_the_capture(monkeypatch):
    _stub(monkeypatch, raises=True)
    store = _Store()
    created = captures.insert_memo_row(store, {"user_id": "u1", "company_id": "co-1"}, pin_playbook=True)
    assert created["id"] == "memo-1"
    assert "playbook_version_id" not in store.inserted[0]


def test_without_the_opt_in_nothing_is_pinned(monkeypatch):
    seen = _stub(monkeypatch, fields={"playbook_version_id": "v-7"})
    store = _Store()
    captures.insert_memo_row(store, {"user_id": "u1", "company_id": "co-1"})
    assert "playbook_version_id" not in store.inserted[0]
    assert seen == {}
