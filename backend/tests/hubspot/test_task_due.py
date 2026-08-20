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


def test_format_catalan_contact_follow_up_title():
    formatted = format_next_step_task(
        "Contactar al setembre per parlar amb tranquil·litat",
        contact_name="Leire Garin",
    )
    assert formatted.subject == "Llamada con Leire"
    assert formatted.task_type == "CALL"


def test_detected_task_due_principios_septiembre(monkeypatch):
    fixed = datetime(2026, 8, 15, 10, 0, tzinfo=TASK_DUE_TZ)
    monkeypatch.setattr("app.services.hubspot.tasks._task_tz_now", lambda: fixed)
    iso = detected_task_due_iso(
        "Contactar a principios de septiembre",
        "principios de septiembre",
    )
    assert iso == "2026-09-01"


def test_format_next_step_task_september_start():
    fixed = datetime(2026, 8, 15, 10, 0, tzinfo=TASK_DUE_TZ)
    import app.services.hubspot.tasks as tasks_mod
    original = tasks_mod._task_tz_now
    tasks_mod._task_tz_now = lambda: fixed
    try:
        formatted = format_next_step_task(
            "Contactar al setembre per parlar amb tranquil·litat",
            schedule_hint="principios de septiembre",
        )
    finally:
        tasks_mod._task_tz_now = original
    assert formatted.due_date.date().isoformat() == "2026-09-01"
    assert formatted.due_date.hour == 9


def test_build_task_body_keeps_original_step_when_title_is_short():
    from app.services.hubspot.tasks import build_task_body

    body = build_task_body(
        step="Contactar al setembre per parlar amb tranquil·litat",
        summary="## Context\n- Busy now",
        formatted_subject="Llamada con Leire",
    )
    assert "Contactar al setembre per parlar amb tranquil·litat" in body
    assert "## Context" in body
    assert "---" in body


def test_build_task_body_skips_duplicate_step_when_same_as_title():
    from app.services.hubspot.tasks import build_task_body

    body = build_task_body(
        step="Llamada de seguimiento",
        summary="Note body",
        formatted_subject="Llamada de seguimiento",
    )
    assert "Llamada de seguimiento" not in body.split("---")[0]
    assert "Note body" in body
