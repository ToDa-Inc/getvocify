"""Where a company's own sales process and the interaction types of each member are kept (migration 084)."""

from __future__ import annotations

import pytest

from app.services.sales_process.store import InMemorySalesProcessStore, SalesProcessUnavailable, SqlSalesProcessStore
from tests.reporting.fake_db import FakeDB

CO, OTHER = "co-1", "co-2"
STEPS = [
    {"key": "cold", "position": 1, "stage": "first_contact"},
    {"key": "discovery", "position": 2, "stage": "first_contact"},
    {"key": "demo", "position": 3, "stage": "deal"},
]


@pytest.fixture(params=["memory", "sql"])
def store(request):
    return InMemorySalesProcessStore() if request.param == "memory" else SqlSalesProcessStore(FakeDB())


def test_a_company_with_no_process_has_an_empty_one(store):
    assert store.list_process(CO) == []


def test_the_process_comes_back_in_order_and_replacing_it_drops_what_is_no_longer_there(store):
    store.replace_process(CO, [STEPS[2], STEPS[0], STEPS[1]])
    assert [r["key"] for r in store.list_process(CO)] == ["cold", "discovery", "demo"]
    assert [r["goal"] for r in store.list_process(CO)] == [None, None, None]  # a row saved without a goal has none
    store.replace_process(CO, [{"key": "demo", "position": 1, "stage": "deal", "goal": "Cerrar la venta"}])
    assert store.list_process(CO) == [{"key": "demo", "position": 1, "stage": "deal", "goal": "Cerrar la venta"}]


def test_the_goal_of_a_type_and_the_calls_outside_the_funnel_are_kept(store):
    store.replace_process(CO, [
        {"key": "cold", "position": 1, "stage": "first_contact", "goal": "Crear interés y acordar una reunión"},
        {"key": "sac", "position": 2, "stage": "other", "goal": None},
    ])
    assert store.list_process(CO) == [
        {"key": "cold", "position": 1, "stage": "first_contact", "goal": "Crear interés y acordar una reunión"},
        {"key": "sac", "position": 2, "stage": "other", "goal": None},
    ]


def test_a_company_never_sees_another_companys_process_or_members(store):
    store.replace_process(CO, STEPS)
    store.set_member_types(CO, ["cold"], user_id="u1")
    assert store.list_process(OTHER) == [] and store.get_member_types(OTHER, user_id="u1") is None


def test_a_member_and_an_invitation_keep_their_types_and_none_means_all(store):
    assert store.get_member_types(CO, user_id="u1") is None
    store.set_member_types(CO, ["cold", "demo"], user_id="u1")
    store.set_member_types(CO, ["discovery"], invitation_id="i1")
    assert store.get_member_types(CO, user_id="u1") == ["cold", "demo"]
    assert store.get_member_types(CO, invitation_id="i1") == ["discovery"]
    store.set_member_types(CO, ["cold"], user_id="u1")
    assert store.get_member_types(CO, user_id="u1") == ["cold"]  # a second save replaces
    store.set_member_types(CO, None, user_id="u1")
    assert store.get_member_types(CO, user_id="u1") is None


def test_dropping_a_type_takes_it_out_of_every_list_and_an_empty_list_becomes_all(store):
    store.replace_process(CO, STEPS)
    store.set_member_types(CO, ["cold", "demo"], user_id="u1")
    store.set_member_types(CO, ["demo"], user_id="u2")
    store.set_member_types(CO, ["demo", "cold"], invitation_id="i1")
    store.drop_type(CO, "demo")
    assert store.get_member_types(CO, user_id="u1") == ["cold"]
    assert store.get_member_types(CO, user_id="u2") is None
    assert store.get_member_types(CO, invitation_id="i1") == ["cold"]
    assert "demo" not in [r["key"] for r in store.list_process(CO)]


def test_a_member_row_needs_a_user_or_an_invitation(store):
    with pytest.raises(ValueError):
        store.set_member_types(CO, ["cold"])


class Missing(FakeDB):
    def table(self, name):
        raise RuntimeError(f"Could not find the table 'public.{name}' in the schema cache")


def test_before_the_tables_exist_the_store_says_so_and_nothing_else():
    sql = SqlSalesProcessStore(Missing())
    with pytest.raises(SalesProcessUnavailable):
        sql.list_process(CO)
    with pytest.raises(SalesProcessUnavailable):
        sql.get_member_types(CO, user_id="u1")


def test_the_members_and_invitations_of_a_company_can_be_listed_together(store):
    store.set_member_types(CO, ["cold"], user_id="u1")
    store.set_member_types(CO, None, user_id="u2")
    store.set_member_types(CO, ["demo"], invitation_id="i1")
    store.set_member_types(OTHER, ["cold"], user_id="u9")
    assert store.list_member_types(CO) == {"members": {"u1": ["cold"], "u2": None}, "invitations": {"i1": ["demo"]}}
