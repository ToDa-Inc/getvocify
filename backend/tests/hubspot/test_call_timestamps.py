from app.services.hubspot.calls import parse_call_summary, parse_hubspot_timestamp_ms


def test_parse_hubspot_timestamp_ms_from_epoch_ms():
    assert parse_hubspot_timestamp_ms("1700000000000") == 1700000000000


def test_parse_hubspot_timestamp_ms_from_iso():
    ms = parse_hubspot_timestamp_ms("2026-08-19T13:35:00.000Z")
    assert ms is not None
    assert ms > 0


def test_parse_call_summary_falls_back_to_created_at():
    summary = parse_call_summary({
        "id": "123",
        "createdAt": "2026-08-19T13:35:00.000Z",
        "properties": {
            "hs_call_recording_url": "https://example.com/rec.mp3",
            "hs_call_title": "Call with Leire Garin",
        },
    })
    assert summary["timestamp_ms"] is not None
    assert summary["timestamp"]
    assert summary["title"] == "Call with Leire Garin"


def test_parse_call_summary_parses_iso_hs_timestamp():
    summary = parse_call_summary({
        "id": "456",
        "properties": {
            "hs_call_recording_url": "https://example.com/rec.mp3",
            "hs_timestamp": "2026-08-19T13:35:00.000Z",
        },
    })
    assert summary["timestamp_ms"] is not None
    assert summary["timestamp"]
