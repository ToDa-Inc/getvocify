"""What the day's backfill would do with each of a rep's calls (2026-10-28, Toni's day in HubSpot)."""

from scripts.backfill_crm_calls import plan_backfill


def _call(call_id, ms, *, recording=True, at=0):
    props = {"hs_call_duration": str(ms), "hs_timestamp": str(1_800_000_000_000 + at)}
    if recording:
        props["hs_call_recording_url"] = "https://rec"
    return {"id": call_id, "properties": props}


def test_each_call_gets_the_action_its_memo_and_length_call_for():
    calls = [
        _call("javier", 169_000, at=5),     # transcribed, but filed under the manager
        _call("marc-2s", 2_000, at=4),      # the short one, also under the manager
        _call("jesus", 386_000, at=3),      # no memo, a real conversation
        _call("lorenzo", 2_000, at=2),      # no memo, two seconds
        _call("judit", 121_000, at=1),      # the rep's own memo
        _call("samy", 0, recording=False),  # NO_ANSWER, nothing recorded
        _call("eduardo", 61_000, at=6),     # the rep's memo, failed: retried
    ]
    memos = {
        "javier": {"id": "m1", "user_id": "dani", "status": "pending_review"},
        "marc-2s": {"id": "m2", "user_id": "dani", "status": "pending_review"},
        "judit": {"id": "m3", "user_id": "toni", "status": "pending_review"},
        "eduardo": {"id": "m4", "user_id": "toni", "status": "failed"},
    }
    plan = {a["call_id"]: a["action"] for a in plan_backfill(calls, memos, "toni")}
    assert plan == {
        "javier": "reassign",
        "marc-2s": "reassign",
        "jesus": "transcribe",
        "lorenzo": "mark_no_answer",
        "judit": "ok",
        "samy": "no_recording",
        "eduardo": "transcribe",
    }


def test_the_plan_reads_oldest_first():
    plan = plan_backfill([_call("b", 5_000, at=9), _call("a", 5_000, at=1)], {}, "toni")
    assert [a["call_id"] for a in plan] == ["a", "b"]
