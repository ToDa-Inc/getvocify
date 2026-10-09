"""The record on screen becomes the contact of the call."""

from app.services.live_calls.crm_url import CrmRecord
from app.services.live_calls.state import end_call, pick_contact, start_call


def _record(object_type="contact", record_id="901", provider="hubspot", account_id="147506535"):
    return CrmRecord(provider=provider, object_type=object_type, record_id=record_id, account_id=account_id)


def test_contact_record_is_the_calls_contact():
    call = start_call("c1", _record(), 1010.0, connected_account_id="147506535")
    assert (call.contact_id, call.contact_source, call.provider) == ("901", "page", "hubspot")
    assert call.record.record_id == "901"
    assert call.to_dict()["needs_contact"] is False


def test_deal_record_is_kept_and_asks_for_the_contact():
    call = start_call("c1", _record(object_type="deal", record_id="55"), 1010.0)
    assert call.contact_id is None and call.record.object_type == "deal"
    assert call.to_dict()["needs_contact"] is True


def test_record_from_another_account_is_not_used():
    call = start_call("c1", _record(account_id="999"), 1010.0, connected_account_id="147506535")
    assert call.contact_id is None and call.record is None


def test_unknown_account_on_either_side_still_assigns():
    assert start_call("c1", _record(account_id=None), 1.0, connected_account_id="147506535").contact_id == "901"
    assert start_call("c1", _record(), 1.0, connected_account_id=None).contact_id == "901"


def test_pipedrive_domain_compare_ignores_case():
    call = start_call("c1", _record(provider="pipedrive", account_id="acme"), 1.0, connected_account_id="Acme")
    assert (call.provider, call.contact_id) == ("pipedrive", "901")


def test_nothing_on_screen_means_no_contact():
    call = start_call("c1", None, 1010.0)
    assert call.contact_id is None and call.is_live


def test_kind_is_kept_with_or_without_a_record():
    assert start_call("c1", _record(), 1.0, kind="meeting").kind == "meeting"
    assert start_call("c1", None, 1.0, kind="meeting").kind == "meeting"
    assert start_call("c1", None, 1.0).kind == "call"


def test_pick_and_end():
    call = pick_contact(start_call("c1", _record(object_type="deal"), 1010.0), "hubspot", "77")
    assert (call.contact_id, call.contact_source) == ("77", "picked")
    ended = end_call(call, 1100.0)
    assert (ended.status, ended.ended_at) == ("ended", 1100.0)
    assert end_call(ended, 2000.0).ended_at == 1100.0
