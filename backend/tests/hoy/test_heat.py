"""T5: heat_score is a pure 0-100 second-order ranking signal inside a Hoy tier."""

from app.services.hoy.heat import heat_score


def test_no_facts_scores_zero():
    assert heat_score({}) == 0


def test_interest_weighs_by_level():
    cold = heat_score({"interest": "none"})
    low = heat_score({"interest": "low"})
    medium = heat_score({"interest": "medium"})
    high = heat_score({"interest": "high"})
    assert cold == 0
    assert cold < low < medium < high


def test_pain_confirmed_and_open_objection_each_add_weight():
    base = heat_score({"interest": "medium"})
    with_pain = heat_score({"interest": "medium", "pain_confirmed": True})
    with_objection = heat_score({"interest": "medium", "objection_open": True})
    both = heat_score({"interest": "medium", "pain_confirmed": True, "objection_open": True})
    assert with_pain > base
    assert with_objection > base
    assert both > with_pain
    assert both > with_objection


def test_recency_makes_a_contact_hotter_and_it_decays():
    fresh = heat_score({"interest": "high", "days_silent": 0})
    a_week = heat_score({"interest": "high", "days_silent": 7})
    stale = heat_score({"interest": "high", "days_silent": 30})
    assert fresh > a_week > stale


def test_email_reply_adds_weight():
    without = heat_score({"interest": "low"})
    replied = heat_score({"interest": "low", "email_replied": True})
    assert replied > without


def test_score_is_clamped_to_0_100():
    assert heat_score({
        "interest": "high",
        "pain_confirmed": True,
        "objection_open": True,
        "days_silent": 0,
        "email_replied": True,
    }) <= 100
    assert heat_score({"days_silent": 999}) >= 0
