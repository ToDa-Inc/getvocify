"""Folding dialer events into one live call."""

from app.services.live_calls.state import LiveCallEvent, apply_event, with_contact


def _event(kind, call_id="ext-1", at=100.0, **extra):
    return LiveCallEvent(
        provider="hubspot",
        source="hubspot_calling_sdk",
        event=kind,
        external_call_id=call_id,
        occurred_at=at,
        **extra,
    )


def test_start_on_contact_page_assigns_that_contact():
    call = apply_event(
        None,
        _event("started", to_number="+34600111222", page_object_type="contact", page_record_id="901"),
    )
    assert call.status == "dialing"
    assert call.contact_id == "901"
    assert call.contact_source == "page"
    assert call.remote_number == "+34600111222"
    assert call.is_open


def test_start_on_deal_page_leaves_contact_for_phone_lookup():
    call = apply_event(
        None,
        _event("started", to_number="+34600111222", page_object_type="deal", page_record_id="55"),
    )
    assert call.contact_id is None
    assert call.page_object_type == "deal"
    assert call.page_record_id == "55"


def test_inbound_remote_number_is_the_caller():
    call = apply_event(
        None,
        _event("started", direction="inbound", from_number="+34911000000", to_number="+34600000000"),
    )
    assert call.remote_number == "+34911000000"


def test_lifecycle_keeps_contact_and_records_times():
    call = apply_event(None, _event("started", at=1.0, page_object_type="contact", page_record_id="7"))
    call = apply_event(call, _event("answered", at=2.0))
    call = apply_event(call, _event("ended", at=9.0, end_status="COMPLETED"))
    call = apply_event(call, _event("completed", at=10.0, engagement_id="4411"))
    assert call.status == "completed"
    assert (call.started_at, call.answered_at, call.ended_at) == (1.0, 2.0, 9.0)
    assert call.end_status == "COMPLETED"
    assert call.engagement_id == "4411"
    assert call.contact_id == "7"
    assert not call.is_open


def test_late_answered_does_not_reopen_an_ended_call():
    call = apply_event(None, _event("started", at=1.0))
    call = apply_event(call, _event("ended", at=5.0))
    call = apply_event(call, _event("answered", at=6.0))
    assert call.status == "ended"
    assert call.answered_at == 6.0


def test_new_call_id_replaces_the_previous_call():
    first = apply_event(None, _event("started", call_id="a", page_object_type="contact", page_record_id="1"))
    second = apply_event(first, _event("started", call_id="b", at=200.0))
    assert second.external_call_id == "b"
    assert second.contact_id is None
    assert second.started_at == 200.0


def test_event_without_prior_start_still_creates_the_call():
    call = apply_event(None, _event("answered", at=3.0, to_number="+34600111222"))
    assert call.status == "connected"
    assert call.answered_at == 3.0
    assert call.remote_number == "+34600111222"


def test_with_contact_marks_phone_source_and_name():
    call = apply_event(None, _event("started", to_number="+34600111222"))
    named = with_contact(call, "88", source="phone", name="María López", now=101.0)
    assert (named.contact_id, named.contact_name, named.contact_source) == ("88", "María López", "phone")
    assert named.updated_at == 101.0


def test_late_start_fills_contact_and_number_but_keeps_status():
    call = apply_event(None, _event("ended", at=5.0, end_status="COMPLETED"))
    assert call.contact_id is None
    call = apply_event(
        call,
        _event("started", at=6.0, to_number="+34600111222", page_object_type="contact", page_record_id="42"),
    )
    assert call.status == "ended"
    assert call.contact_id == "42"
    assert call.contact_source == "page"
    assert call.remote_number == "+34600111222"


def test_known_contact_is_never_overwritten_by_a_later_page():
    call = apply_event(None, _event("started", page_object_type="contact", page_record_id="1"))
    call = apply_event(call, _event("answered", page_object_type="contact", page_record_id="2"))
    assert call.contact_id == "1"
