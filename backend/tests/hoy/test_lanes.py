"""F18–F21: which Hoy lane a contact belongs to, and who may see it."""

from app.services.hoy.lanes import default_motion, keep_lane, lane_for_exit, motions_for, visible_lanes


def test_h7_ended_is_hidden():
    assert lane_for_exit("ended") is None
    assert keep_lane(None, ("calls", "meetings")) is False


def test_h2_sdr_does_not_see_booked():
    lane = lane_for_exit("booked")
    assert lane == "meetings"
    assert keep_lane(lane, visible_lanes("sdr", "member")) is False


def test_h3_ae_sees_booked_not_calls():
    lanes = visible_lanes("ae", "member")
    assert keep_lane(lane_for_exit("booked"), lanes) is True
    assert keep_lane(lane_for_exit(None), lanes) is False


def test_h4_ae_without_state_is_a_call_and_hidden():
    assert lane_for_exit(None) == "calls"
    assert keep_lane("calls", visible_lanes("ae", "member")) is False


def test_h5_h6_general_sees_both_lanes():
    lanes = visible_lanes("general", "member")
    assert keep_lane("meetings", lanes) is True
    assert keep_lane("calls", lanes) is True


def test_a1_admin_sees_both_whatever_their_sales_role():
    assert visible_lanes("sdr", "admin") == ("calls", "meetings")
    assert visible_lanes("ae", "owner") == ("calls", "meetings")


def test_p1_p2_p3_motions():
    assert motions_for("sdr", "member") == ("discovery", "qualification")
    assert motions_for("ae", "member") == ("closing",)
    assert motions_for("sdr", "admin") == ("discovery", "qualification", "closing")
    assert motions_for("general", "member") == ("discovery", "qualification", "closing")


def test_y1_sdr_keeps_calls_and_drops_the_meeting():
    from app.services.hoy.lanes import partition_by_lane

    calls, meetings = partition_by_lane(
        [{"contact_id": "c1"}, {"contact_id": "c2"}],
        {"c2": "booked"},
        "sdr",
        "member",
    )
    assert [row["contact_id"] for row in calls] == ["c1"]
    assert meetings == []


def test_y2_ae_keeps_only_the_meeting():
    from app.services.hoy.lanes import partition_by_lane

    calls, meetings = partition_by_lane(
        [{"contact_id": "c1"}, {"contact_id": "c2"}],
        {"c2": "booked"},
        "ae",
        "member",
    )
    assert calls == []
    assert [row["contact_id"] for row in meetings] == ["c2"]
    assert meetings[0]["lane"] == "meetings"


def test_a1_admin_sees_the_sdr_call_and_the_ae_meeting():
    from app.services.hoy.lanes import partition_by_lane

    calls, meetings = partition_by_lane(
        [{"contact_id": "c1", "user_id": "sdr"}, {"contact_id": "c2", "user_id": "ae"}],
        {"c2": "booked", "c3": "ended"},
        "general",
        "admin",
    )
    assert [row["contact_id"] for row in calls] == ["c1"]
    assert [row["contact_id"] for row in meetings] == ["c2"]


def test_p4_default_motion_only_for_sdr_and_ae():
    assert default_motion("sdr", "member") == "discovery"
    assert default_motion("ae", "member") == "closing"
    assert default_motion("general", "member") is None
    assert default_motion("sdr", "admin") is None
