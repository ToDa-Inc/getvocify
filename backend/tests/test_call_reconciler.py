"""Calls whose Twilio callbacks were lost are found and finished; everything else is left alone."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.telephony import call_reconciler

NOW = datetime(2026, 10, 14, 16, 0, tzinfo=timezone.utc)


class _Query:
    def __init__(self, rows, calls):
        self.rows = rows
        self.calls = calls

    def __getattr__(self, name):
        def step(*args, **kwargs):
            self.calls.append((name, args))
            return self

        return step

    def execute(self):
        return SimpleNamespace(data=self.rows)


def _supabase(rows):
    calls = []
    client = MagicMock()
    client.table.side_effect = lambda name: _Query(rows, calls)
    return client, calls


def _recording(**overrides):
    values = {
        "sid": "RE1",
        "status": "completed",
        "duration": "343",
        "start_time": NOW - timedelta(minutes=20),
        "uri": "/2010-04-01/Accounts/AC1/Recordings/RE1.json",
    }
    return SimpleNamespace(**{**values, **overrides})


@pytest.fixture(autouse=True)
def _fresh():
    call_reconciler._settled.clear()
    yield
    call_reconciler._settled.clear()


async def _sweep(rows, view, *, now=NOW):
    supabase, calls = _supabase(rows)
    twilio = MagicMock(side_effect=view if callable(view) else lambda sid: view)
    with (
        patch.object(call_reconciler, "_twilio_view", twilio),
        patch("app.api.webhooks.start_recording_job", MagicMock(return_value=True)) as start,
        patch("app.services.telephony.call_processor.log_missed_call_activity", AsyncMock()) as missed,
    ):
        recovered = await call_reconciler.reconcile_calls(supabase, now=now)
    return SimpleNamespace(recovered=recovered, start=start, missed=missed, twilio=twilio, calls=calls)


async def test_only_settled_twilio_calls_without_a_recording_are_looked_at():
    result = await _sweep([], {"recording": None})
    filters = {(name, args) for name, args in result.calls}
    assert ("eq", ("status", "dialing")) in filters
    assert ("eq", ("carrier", "twilio")) in filters
    assert ("is_", ("recording_path", "null")) in filters
    assert ("lt", ("created_at", (NOW - call_reconciler.SETTLE).isoformat())) in filters
    assert ("gt", ("created_at", (NOW - call_reconciler.LOOK_BACK).isoformat())) in filters


async def test_a_call_whose_recording_callback_was_lost_gets_it_processed():
    result = await _sweep([{"carrier_call_id": "CA1"}], {"recording": _recording()})

    assert result.recovered == 1
    args, kwargs = result.start.call_args
    assert args[1:] == ("CA1", "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/RE1")
    assert kwargs == {
        "recording_sid": "RE1",
        "duration": 343.0,
        "started_at": NOW - timedelta(minutes=20),
    }


async def test_a_call_still_on_the_phone_is_left_alone():
    view = {"recording": None, "status": "in-progress", "ended_at": None, "dial_status": "in-progress"}
    result = await _sweep([{"carrier_call_id": "CA1"}], view)
    again = await _sweep([{"carrier_call_id": "CA1"}], view)

    assert result.recovered == 0
    result.start.assert_not_called()
    result.missed.assert_not_called()
    again.twilio.assert_called_once()  # asked again next sweep


async def test_a_missed_call_whose_dial_status_was_lost_is_logged_once():
    view = {"recording": None, "status": "completed", "ended_at": NOW - timedelta(minutes=5), "dial_status": "no-answer"}
    first = await _sweep([{"carrier_call_id": "CA1", "call_disposition": None}], view)
    second = await _sweep([{"carrier_call_id": "CA1", "call_disposition": None}], view)

    first.missed.assert_awaited_once()
    assert first.missed.call_args.args[1:] == ("CA1", "no-answer")
    second.twilio.assert_not_called()


async def test_a_missed_call_already_logged_is_not_logged_again():
    view = {"recording": None, "status": "completed", "ended_at": NOW - timedelta(minutes=5), "dial_status": "busy"}
    result = await _sweep([{"carrier_call_id": "CA1", "call_disposition": "busy"}], view)

    result.missed.assert_not_called()
    assert result.recovered == 0


async def test_an_answered_call_waits_for_twilio_to_finish_its_recording():
    def view(ended_minutes_ago):
        return {
            "recording": None,
            "status": "completed",
            "ended_at": NOW - timedelta(minutes=ended_minutes_ago),
            "dial_status": "completed",
        }

    soon = await _sweep([{"carrier_call_id": "CA1"}], view(5))
    later = await _sweep([{"carrier_call_id": "CA1"}], view(5))
    given_up = await _sweep([{"carrier_call_id": "CA1"}], view(45))
    after = await _sweep([{"carrier_call_id": "CA1"}], view(45))

    later.twilio.assert_called_once()  # still within the grace: asked again
    given_up.twilio.assert_called_once()
    after.twilio.assert_not_called()  # past the grace: settled
    soon.start.assert_not_called()


async def test_one_failed_twilio_lookup_does_not_stop_the_sweep():
    def view(sid):
        if sid == "CA1":
            raise RuntimeError("twilio 500")
        return {"recording": _recording(sid="RE2")}

    result = await _sweep([{"carrier_call_id": "CA1"}, {"carrier_call_id": "CA2"}], view)

    assert result.recovered == 1
    assert result.start.call_args.args[1] == "CA2"
