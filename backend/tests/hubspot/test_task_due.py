from datetime import datetime, timedelta

from app.services.hubspot.tasks import (
    TASK_DUE_TZ,
    detected_task_due_iso,
    format_next_step_task,
    normalize_task_due_datetime,
)


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


def test_format_next_step_task_defaults_iso_date_to_9am_madrid():
    formatted = format_next_step_task("Follow up", schedule_hint="2026-08-20")
    assert formatted.due_date.tzinfo == TASK_DUE_TZ
    assert formatted.due_date.hour == 9
    assert formatted.due_date.minute == 0
    assert formatted.due_date.date().isoformat() == "2026-08-20"


def test_format_next_step_task_keeps_explicit_spoken_time():
    formatted = format_next_step_task("Llamar mañana a las 18:00", schedule_hint="mañana")
    assert formatted.due_date.tzinfo == TASK_DUE_TZ
    assert formatted.due_date.hour == 18
    assert formatted.due_date.minute == 0


def test_normalize_task_due_datetime_moves_midnight_to_9am():
    naive = datetime(2026, 8, 20)
    normalized = normalize_task_due_datetime(naive)
    assert normalized.hour == 9
    assert normalized.tzinfo == TASK_DUE_TZ
