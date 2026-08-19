from datetime import datetime, timedelta

from app.services.hubspot.tasks import detected_task_due_iso


def test_detected_task_due_iso_parses_tomorrow():
    iso = detected_task_due_iso("Send one-pager", "mañana")
    expected = (datetime.utcnow() + timedelta(days=1)).date().isoformat()
    assert iso == expected


def test_detected_task_due_iso_keeps_explicit_calendar_date():
    assert detected_task_due_iso("Follow up", "2026-08-20") == "2026-08-20"


def test_detected_task_due_iso_is_empty_without_timing():
    assert detected_task_due_iso("Send one-pager", "") is None
    assert detected_task_due_iso("Send one-pager") is None
    assert detected_task_due_iso("Send one-pager", None) is None
