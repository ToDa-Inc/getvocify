from datetime import datetime, timezone

from app.services.hoy.materialize import fresh_signals, retracted_objection_ids


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


def test_intelligence_with_no_objections_overrides_the_legacy_text():
    signals = fresh_signals(
        [{
            "id": "memo-1",
            "hubspot_contact_id": "42",
            "capture_started_at": "2026-09-20T10:00:00Z",
            "extraction": {
                "objections": ["No es el mejor momento"],
                "intelligence": {"interest": "high", "objections": []},
            },
        }],
        now=NOW,
        day_end=DAY_END,
    )
    assert "objection_open" not in [signal.type for signal in signals]


def test_only_a_pending_objection_of_a_reread_memo_is_retracted():
    existing = [
        {"id": "a", "type": "objection_open", "status": "pending", "memo_id": "memo-1", "dedupe_key": "objection:memo-1:other"},
        {"id": "b", "type": "objection_open", "status": "pending", "memo_id": "memo-1", "dedupe_key": "objection:memo-1:price"},
        {"id": "c", "type": "objection_open", "status": "pending", "memo_id": "memo-old", "dedupe_key": "objection:memo-old:other"},
        {"id": "d", "type": "objection_open", "status": "done", "memo_id": "memo-1", "dedupe_key": "objection:memo-1:timing"},
        {"id": "e", "type": "going_cold", "status": "pending", "memo_id": "memo-1", "dedupe_key": "cold:42"},
    ]
    kept = {"objection:memo-1:price"}
    assert retracted_objection_ids(existing, memo_ids={"memo-1"}, fresh_keys=kept) == ["a"]
