"""Which reps are transcribing live: the recording webhook waits for their live transcript."""

from app.services import live_activity


def setup_function():
    live_activity._open.clear()
    live_activity._ended_at.clear()


def test_a_rep_with_an_open_session_is_live():
    live_activity.session_started("rep-1")
    assert live_activity.recently_live("rep-1")
    assert not live_activity.recently_live("rep-2")


def test_a_session_that_just_ended_still_counts_for_a_while(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(live_activity.time, "monotonic", lambda: now[0])
    live_activity.session_started("rep-1")
    live_activity.session_ended("rep-1")
    now[0] += 30
    assert live_activity.recently_live("rep-1")
    now[0] += live_activity.RECENT_S
    assert not live_activity.recently_live("rep-1")


def test_two_sessions_keep_the_rep_live_until_both_end():
    live_activity.session_started("rep-1")
    live_activity.session_started("rep-1")
    live_activity.session_ended("rep-1")
    assert live_activity._open["rep-1"] == 1
    live_activity.session_ended("rep-1")
    assert "rep-1" not in live_activity._open


def test_no_user_is_never_live():
    live_activity.session_started(None)
    live_activity.session_ended(None)
    assert not live_activity.recently_live(None)
