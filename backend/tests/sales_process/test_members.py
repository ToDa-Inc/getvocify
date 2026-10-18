"""Which interaction types each member runs: assigned when inviting or from their profile, and the role the rest of the
product reads (SDR / AE / general) follows from them."""

from __future__ import annotations

import pytest

from app.api.sales_process import ProcessType, apply_process
from app.services import feature_flags
from app.services.playbooks.repository import InMemoryPlaybookRepository
from app.services.sales_process.members import carry_invite_types, derive_for_invite
from app.services.sales_process.store import InMemorySalesProcessStore
from tests.sales_process.test_api import BASE, make_client, put, t  # noqa: F401 (autouse fixtures live there)
from tests.sales_process.test_api import _clean  # noqa: F401
from tests.reporting.fake_db import FakeDB

CO = "co-1"


def company_db(members):
    flags = [{"company_id": CO, "flag": "SALES_ROLES_ENABLED", "enabled": True}]
    return FakeDB({"company_members": members, "company_feature_flags": flags})


def member(user_id, role="member", sales_role=None):
    return {"id": f"row-{user_id}", "company_id": CO, "user_id": user_id, "role": role, "status": "active", "sales_role": sales_role, "handoff_ae_user_id": None, "visibility": "own"}


def two_types(client):
    types = put(client, t("Llamada en frío"), t("Demo", "deal")).json()["types"]
    return types[0]["key"], types[1]["key"]


def test_choosing_what_a_member_runs_sets_their_types_and_the_role_that_follows():
    db = company_db([member("u2")])
    client = make_client(db=db)
    cold, demo = two_types(client)
    done = client.put(f"{BASE}/members/row-u2", json={"types": [cold]})
    assert done.status_code == 200 and done.json() == {"types": [cold], "sales_role": "sdr"}
    assert db.tables["company_members"][0]["sales_role"] == "sdr"
    assert client.put(f"{BASE}/members/row-u2", json={"types": [demo]}).json()["sales_role"] == "ae"
    assert client.put(f"{BASE}/members/row-u2", json={"types": [cold, demo]}).json()["sales_role"] == "general"
    back = client.put(f"{BASE}/members/row-u2", json={"types": None}).json()
    assert back == {"types": None, "sales_role": "general"} and db.tables["company_members"][0]["sales_role"] == "general"


def test_the_list_says_what_every_member_and_invitation_runs():
    client = make_client(db=company_db([member("u2"), member("u3")]))
    cold, demo = two_types(client)
    client.put(f"{BASE}/members/row-u2", json={"types": [cold]})
    got = client.get(f"{BASE}/members").json()
    assert got["members"] == {"u2": [cold]}


def test_types_that_do_not_exist_are_ignored_and_an_empty_choice_means_all():
    client = make_client(db=company_db([member("u2")]))
    cold, _ = two_types(client)
    assert client.put(f"{BASE}/members/row-u2", json={"types": ["ghost", cold]}).json()["types"] == [cold]
    assert client.put(f"{BASE}/members/row-u2", json={"types": ["ghost"]}).json()["types"] is None
    assert client.put(f"{BASE}/members/row-u2", json={"types": []}).json()["types"] is None


def test_only_a_manager_and_only_for_a_member_of_the_company():
    assert make_client(role="member", db=company_db([member("u2")])).put(f"{BASE}/members/row-u2", json={"types": None}).status_code == 403
    client = make_client(db=company_db([member("u2")]))
    two_types(client)
    assert client.put(f"{BASE}/members/row-nobody", json={"types": None}).status_code in (404, 500)


def test_an_invitation_keeps_what_the_new_member_will_run_and_hands_it_over_when_accepted():
    store, repository = InMemorySalesProcessStore(), InMemoryPlaybookRepository()
    apply_process(repository, store, CO, [
        ProcessType(label="Llamada en frío", stage="first_contact", goal="Conseguir una reunión", recognize="Primer contacto"),
        ProcessType(label="Demo", stage="deal", goal="Cerrar", recognize="Con el decisor"),
    ])
    cold = store.list_process(CO)[0]["key"]
    types, role = derive_for_invite(store, repository, CO, [cold, "ghost"])
    assert (types, role) == ([cold], "sdr")
    store.set_member_types(CO, types, invitation_id="inv-1")
    carry_invite_types(store, CO, "inv-1", "new-user")
    assert store.get_member_types(CO, user_id="new-user") == [cold]
    assert store.get_member_types(CO, invitation_id="inv-1") is None  # handed over, not duplicated
    assert derive_for_invite(store, repository, CO, None) == (None, "general")


def test_the_invitation_form_hooks_do_nothing_without_the_flag_or_without_types(monkeypatch):
    from app.config import settings
    from app.services.sales_process.members import before_invite, hand_over_invite_types, keep_invite_types
    from app.services.sales_process.store import get_sales_process_store

    client = make_client()
    cold, _ = two_types(client)
    db = FakeDB()
    assert before_invite(db, CO, None) == (None, None)  # nothing said
    assert before_invite(db, CO, [cold]) == ([cold], "sdr")  # the fixture switches the flag on
    monkeypatch.setattr(settings, "SALES_PROCESS_ENABLED", False)
    feature_flags.clear_cache()
    assert before_invite(db, CO, [cold]) == (None, None)  # flag off: the invitation goes as it always did
    keep_invite_types(db, CO, "inv-9", [cold])
    hand_over_invite_types(db, CO, "inv-9", "new-user")
    assert get_sales_process_store(db).get_member_types(CO, user_id="new-user") == [cold]
    hand_over_invite_types(db, CO, "no-such-invitation", "someone")  # never raises
