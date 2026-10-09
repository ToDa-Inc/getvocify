"""T3 D7: find_owner_id (reuses hoy/assigned.py's owners_request shape) and
apply_owner_handoff (skipped/unmapped/done/failed)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-handoffs-32c")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-handoffs-32c")

from app.services.handoffs_crm import apply_owner_handoff, find_owner_id, owner_writer_from_connection


def _hubspot_fetch(pages):
    calls = {"n": 0}

    def fetch(_request):
        page = pages[calls["n"]]
        calls["n"] += 1
        return page

    return fetch


def test_find_owner_id_matches_case_insensitively_across_pages():
    pages = [
        {"results": [{"id": "1", "email": "Other@x.com"}], "paging": {"next": {"after": "c1"}}},
        {"results": [{"id": "2", "email": "ae@x.com"}]},
    ]
    fetch = _hubspot_fetch(pages)
    assert find_owner_id(fetch, "hubspot", "AE@X.com") == "2"


def test_find_owner_id_none_when_not_found():
    fetch = _hubspot_fetch([{"results": [{"id": "1", "email": "other@x.com"}]}])
    assert find_owner_id(fetch, "hubspot", "ae@x.com") is None


def test_find_owner_id_none_on_error_kind():
    fetch = _hubspot_fetch([{"error_kind": "auth_expired"}])
    assert find_owner_id(fetch, "hubspot", "ae@x.com") is None


def test_find_owner_id_pipedrive_uses_data_key():
    fetch = _hubspot_fetch([{"data": [{"id": 7, "email": "ae@x.com"}]}])
    assert find_owner_id(fetch, "pipedrive", "ae@x.com") == "7"


class _FakeSupabaseAuth:
    def __init__(self, email):
        self._email = email

    class _Admin:
        def __init__(self, outer):
            self._outer = outer

        def get_user_by_id(self, _user_id):
            if self._outer._email is None:
                raise RuntimeError("not found")
            return type("U", (), {"user": type("Inner", (), {"email": self._outer._email})()})()

    @property
    def admin(self):
        return self._Admin(self)


class _FakeSupabase:
    def __init__(self, email):
        self.auth = _FakeSupabaseAuth(email)


class _FakeWriter:
    def __init__(self, owner_id, set_ok=True):
        self._owner_id = owner_id
        self._set_ok = set_ok
        self.set_calls = []

    def find_owner_id(self, email):
        return self._owner_id

    def set_owner(self, *, object_type, object_id, owner_id):
        self.set_calls.append((object_type, object_id, owner_id))
        return self._set_ok


def test_apply_owner_handoff_skipped_without_a_writer():
    supabase = _FakeSupabase("ae@x.com")
    status = apply_owner_handoff(supabase, connection={}, ae_user_id="ae-1", deal_id="d1", contact_id="c1")
    assert status == "skipped"


def test_apply_owner_handoff_unmapped_without_an_email():
    supabase = _FakeSupabase(None)
    writer = _FakeWriter("owner-1")
    status = apply_owner_handoff(
        supabase, connection={"provider": "hubspot"}, ae_user_id="ae-1", deal_id="d1", contact_id="c1", writer=writer,
    )
    assert status == "unmapped"
    assert writer.set_calls == []


def test_apply_owner_handoff_unmapped_without_a_matching_owner():
    supabase = _FakeSupabase("ae@x.com")
    writer = _FakeWriter(None)
    status = apply_owner_handoff(
        supabase, connection={"provider": "hubspot"}, ae_user_id="ae-1", deal_id="d1", contact_id="c1", writer=writer,
    )
    assert status == "unmapped"


def test_apply_owner_handoff_done_writes_the_deal_owner():
    supabase = _FakeSupabase("ae@x.com")
    writer = _FakeWriter("owner-9")
    status = apply_owner_handoff(
        supabase, connection={"provider": "hubspot"}, ae_user_id="ae-1", deal_id="d1", contact_id="c1", writer=writer,
    )
    assert status == "done"
    assert writer.set_calls == [("deal", "d1", "owner-9")]


def test_apply_owner_handoff_writes_the_contact_when_there_is_no_deal():
    supabase = _FakeSupabase("ae@x.com")
    writer = _FakeWriter("owner-9")
    status = apply_owner_handoff(
        supabase, connection={"provider": "hubspot"}, ae_user_id="ae-1", deal_id=None, contact_id="c1", writer=writer,
    )
    assert status == "done"
    assert writer.set_calls == [("contact", "c1", "owner-9")]


def test_apply_owner_handoff_failed_when_the_write_fails():
    supabase = _FakeSupabase("ae@x.com")
    writer = _FakeWriter("owner-9", set_ok=False)
    status = apply_owner_handoff(
        supabase, connection={"provider": "hubspot"}, ae_user_id="ae-1", deal_id="d1", contact_id="c1", writer=writer,
    )
    assert status == "failed"


def test_owner_writer_from_connection_requires_a_token_and_known_provider():
    assert owner_writer_from_connection({"provider": "hubspot", "access_token": ""}) is None
    assert owner_writer_from_connection({"provider": "salesforce", "access_token": "tok"}) is None
    assert owner_writer_from_connection({"provider": "pipedrive", "access_token": "tok", "metadata": {}}) is None
    writer = owner_writer_from_connection({"provider": "hubspot", "access_token": "tok"})
    assert writer is not None
