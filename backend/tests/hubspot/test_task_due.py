from datetime import datetime, timedelta

from app.services.hubspot.tasks import (
    TASK_DUE_TZ,
    detected_task_due_iso,
    format_next_step_task,
    normalize_task_due_datetime,
)


def test_detected_task_due_iso_parses_tomorrow():
    iso = detected_task_due_iso("Send one-pager", "mañana")
    expected = (datetime.now(TASK_DUE_TZ) + timedelta(days=1)).date().isoformat()
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


NOW = datetime(2026, 10, 14, 10, 0, tzinfo=TASK_DUE_TZ)  # a Wednesday


def _freeze(monkeypatch):
    monkeypatch.setattr("app.services.hubspot.tasks._task_tz_now", lambda: NOW)


def test_day_of_the_month_is_the_next_one(monkeypatch):
    _freeze(monkeypatch)
    assert detected_task_due_iso("Volver a hablar el día 15") == "2026-10-15"
    assert detected_task_due_iso("Volver a hablar el día 10") == "2026-11-10"


def test_the_last_day_of_the_month_is_this_month(monkeypatch):
    _freeze(monkeypatch)
    assert detected_task_due_iso("Llamar el día 31") == "2026-10-31"


def test_named_month_day_rolls_to_next_year_when_past(monkeypatch):
    _freeze(monkeypatch)
    assert detected_task_due_iso("Llamar el 3 de noviembre") == "2026-11-03"
    assert detected_task_due_iso("Llamar el 3 de marzo") == "2027-03-03"


def test_spans_of_days_and_weeks(monkeypatch):
    _freeze(monkeypatch)
    assert detected_task_due_iso("Seguimiento en 2 semanas") == "2026-10-28"
    assert detected_task_due_iso("Confirmar dentro de 5 días") == "2026-10-19"
    assert detected_task_due_iso("Follow up in 3 days") == "2026-10-17"
    assert detected_task_due_iso("Hablar la semana que viene") == "2026-10-21"


def test_call_title_keeps_what_the_call_is_for(monkeypatch):
    _freeze(monkeypatch)
    formatted = format_next_step_task(
        "Llamar a Juan el martes para confirmar el presupuesto", contact_name="Juan Pérez"
    )
    assert formatted.subject == "Llamada con Juan: confirmar el presupuesto"
    assert formatted.due_date.date().isoformat() == "2026-10-20"


def test_the_date_phrase_never_stays_in_the_title(monkeypatch):
    _freeze(monkeypatch)
    formatted = format_next_step_task("Confirmar precio con el director dentro de 5 días")
    assert formatted.subject == "Confirmar precio con el director"


def test_a_long_step_is_cut_at_a_word_not_replaced_by_a_generic_title(monkeypatch):
    _freeze(monkeypatch)
    step = "Valorar internamente si la integración con el sistema de facturación del cliente encaja con su calendario de despliegue"
    subject = format_next_step_task(step).subject
    assert subject.startswith("Valorar internamente si la integración")
    assert len(subject) <= 81 and subject.endswith("…")
