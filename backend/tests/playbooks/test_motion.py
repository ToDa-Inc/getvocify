"""T2 (D4/D5): the playbook flow a rep's role and interaction land in."""

from app.services.playbooks.motion import GOAL_FOR_MOTION, goal_for, motion_for, visible_to_role


def test_sdr_always_prospects_regardless_of_channel():
    assert motion_for("sdr", "call") == "discovery"
    assert motion_for("sdr", "meeting") == "discovery"
    assert motion_for("sdr", "visit") == "discovery"
    assert motion_for("sdr", "voice_note") == "discovery"


def test_ae_always_closes_regardless_of_channel():
    assert motion_for("ae", "call") == "closing"
    assert motion_for("ae", "meeting") == "closing"
    assert motion_for("ae", "visit") == "closing"
    assert motion_for("ae", "voice_note") == "closing"


def test_general_or_missing_role_follows_the_channel():
    for role in ("general", None, "", "  "):
        assert motion_for(role, "call") == "discovery"
        assert motion_for(role, "meeting") == "closing"
        assert motion_for(role, "visit") == "closing"


def test_unknown_role_falls_back_to_channel_like_general():
    assert motion_for("closer", "call") == "discovery"
    assert motion_for("closer", "meeting") == "closing"


def test_general_or_missing_role_with_no_fixed_channel_has_no_motion():
    """A voice_note (or any other channel) has no fixed flow for general/no role: the
    caller falls back to its existing single-published-playbook rule."""
    for role in ("general", None, "", "  "):
        assert motion_for(role, "voice_note") is None


def test_goal_for_matches_d4_defaults():
    assert goal_for("discovery") == "meeting_booked"
    assert goal_for("closing") == "proposal_and_close"
    assert set(GOAL_FOR_MOTION) == {"discovery", "inbound", "ae_discovery", "closing", "negotiation"}
    assert goal_for("inbound") == "meeting_booked"
    assert goal_for("ae_discovery") == "demo_booked"
    assert goal_for("negotiation") == "close_date"


def test_goal_for_unknown_motion_is_none():
    assert goal_for("qualification") is None
    assert goal_for("outbound") is None


def test_visible_to_role_hides_the_other_flow():
    assert visible_to_role("discovery", "sdr") is True
    assert visible_to_role("closing", "sdr") is False
    assert visible_to_role("discovery", "ae") is False
    assert visible_to_role("closing", "ae") is True


def test_visible_to_role_keeps_everything_for_general_and_custom_motions():
    for role in ("general", None, ""):
        assert visible_to_role("discovery", role) is True
        assert visible_to_role("closing", role) is True
        assert visible_to_role("qualification", role) is True
    assert visible_to_role("qualification", "sdr") is True
    assert visible_to_role("qualification", "ae") is True
