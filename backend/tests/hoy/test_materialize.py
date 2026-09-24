from datetime import datetime, timezone

from app.services.hoy.materialize import fresh_signals


NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
DAY_END = datetime(2026, 9, 24, 21, 59, tzinfo=timezone.utc)


def test_a_stored_open_objection_becomes_one_signal_without_a_model():
    signals = fresh_signals(
        [{
            "id": "memo-1",
            "hubspot_contact_id": "42",
            "capture_started_at": "2026-09-20T10:00:00Z",
            "extraction": {
                "intelligence": {
                    "interest": "high",
                    "objections": [{"resolution": "open", "category": "price", "quote": "Está caro"}],
                }
            },
        }],
        now=NOW,
        day_end=DAY_END,
    )
    assert [signal.type for signal in signals] == ["objection_open"]
    assert signals[0].payload["category"] == "price"
    assert "caro" in signals[0].payload["quote"]
