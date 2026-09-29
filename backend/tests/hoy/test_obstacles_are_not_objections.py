"""An open obstacle (bad moment, wrong person) is a follow-up, not a price or trust objection."""

from datetime import datetime, timedelta, timezone

from app.services.hoy.materialize import fresh_signals

NOW = datetime.now(timezone.utc)


def _memo(objections):
    return {
        "id": "m1", "hubspot_contact_id": "c1", "created_at": (NOW - timedelta(days=2)).isoformat(),
        "extraction": {"intelligence": {"interest": "high", "objections": objections, "commitments": []}},
    }


def _types(memo):
    return [s.type for s in fresh_signals([memo], now=NOW, day_end=NOW + timedelta(hours=8))]


def test_an_open_objection_still_raises_objection_open():
    assert "objection_open" in _types(_memo([{"kind": "objection", "category": "price", "resolution": "open", "quote": "caro"}]))


def test_an_open_obstacle_does_not_raise_objection_open():
    assert "objection_open" not in _types(_memo([{"kind": "obstacle", "category": "bad_moment", "resolution": "open", "quote": "conduciendo"}]))


def test_a_v1_objection_without_a_kind_still_counts():
    assert "objection_open" in _types(_memo([{"category": "price", "resolution": "open", "quote": "caro"}]))
