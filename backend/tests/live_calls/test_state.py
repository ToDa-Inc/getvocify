"""The record a rep has open becomes the contact of the call they start."""

from app.services.live_calls.state import (
    PRESENCE_ASSIGN_SECONDS,
    RecordPresence,
    attach_memo,
    end_call,
    pick_contact,
    start_call,
)


def _presence(object_type="contact", record_id="901", provider="hubspot", account_id="147506535", seen_at=1000.0):
    return RecordPresence(provider=provider, object_type=object_type, record_id=record_id, account_id=account_id, seen_at=seen_at)


def test_contact_page_is_the_calls_contact():
    call = start_call("c1", _presence(), 1010.0, connected_account_id="147506535")
    assert (call.contact_id, call.contact_source, call.provider) == ("901", "page", "hubspot")
    assert call.record.record_id == "901"
    assert call.to_dict()["needs_contact"] is False


def test_deal_page_keeps_the_record_and_asks_for_the_contact():
    call = start_call("c1", _presence(object_type="deal", record_id="55"), 1010.0)
    assert call.contact_id is None
    assert call.record.object_type == "deal"
    assert call.to_dict()["needs_contact"] is True


def test_stale_record_is_not_assigned():
    call = start_call("c1", _presence(seen_at=0.0), PRESENCE_ASSIGN_SECONDS + 1)
    assert call.contact_id is None and call.record is None


def test_record_from_another_account_is_not_assigned():
    call = start_call("c1", _presence(account_id="999"), 1010.0, connected_account_id="147506535")
    assert call.contact_id is None and call.record is None


def test_unknown_account_on_either_side_still_assigns():
    assert start_call("c1", _presence(account_id=None), 1010.0, connected_account_id="147506535").contact_id == "901"
    assert start_call("c1", _presence(), 1010.0, connected_account_id=None).contact_id == "901"


def test_no_record_open_means_no_contact():
    call = start_call("c1", None, 1010.0)
    assert call.contact_id is None and call.is_live


def test_pipedrive_person_is_a_contact_too():
    call = start_call("c1", _presence(provider="pipedrive", account_id="acme"), 1010.0, connected_account_id="acme")
    assert (call.provider, call.contact_id) == ("pipedrive", "901")


def test_pick_end_and_memo():
    call = start_call("c1", _presence(object_type="deal"), 1010.0)
    call = pick_contact(call, "hubspot", "77")
    assert (call.contact_id, call.contact_source) == ("77", "picked")
    call = attach_memo(call, "m1")
    ended = end_call(call, 1100.0)
    assert (ended.status, ended.ended_at, ended.memo_id) == ("ended", 1100.0, "m1")
    assert end_call(ended, 2000.0).ended_at == 1100.0


def test_crm_page_without_a_record_means_no_contact():
    off_record = RecordPresence(provider="hubspot", object_type=None, record_id=None, account_id=None, seen_at=1000.0)
    call = start_call("c1", off_record, 1010.0)
    assert call.contact_id is None and call.record is None
