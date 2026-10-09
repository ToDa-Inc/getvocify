"""F06: reasons stay short and come from one server-side writer."""

from datetime import datetime, timedelta, timezone

from app.services.hoy.reasons import reason
from app.services.hoy.signals import Signal

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


def _cold() -> Signal:
    return Signal(
        type="going_cold",
        contact_id="42",
        deal_id=None,
        source_memo_id="memo-1",
        due_at=None,
        payload={"interest": "high", "days_silent": 12},
        dedupe_key="cold:42",
        connection_id="crm-A",
    )


def test_reasons_are_short_and_match_lang_without_diverging_facts():
    cold = _cold()
    es = reason(cold, lang="es")
    en = reason(cold, lang="en")
    assert len(es) <= 120
    assert len(en) <= 120
    assert "12" in es and "12" in en
    assert es != en


def test_going_cold_wording_only_changes_with_lead_tiers_and_type_never_changes():
    cold = _cold()
    assert reason(cold) == "Mostró mucho interés y lleváis 12 días sin hablar."
    assert reason(cold, lead_tiers=True) == "Mostró mucho interés y lleva 12 días sin hablar."
    assert cold.type == "going_cold"  # T5: persisted type stays going_cold, only the wording is "stale_hot"


def test_callback_no_answer_reason_names_the_outcome_and_days_computed_at_render_time():
    """T5 review: the day count comes from `at` + the `now` passed to reason(), never a
    frozen count on the payload - the same signal reads differently a day later."""
    called = Signal(
        type="callback_no_answer",
        contact_id="42",
        deal_id=None,
        source_memo_id="memo-1",
        due_at=None,
        payload={"outcome": "no_response", "at": (NOW - timedelta(days=3)).isoformat()},
        dedupe_key="callback:memo-1",
    )
    assert reason(called, lang="es", now=NOW) == "Le llamaste hace 3 días y no contestó."
    assert reason(called, lang="en", now=NOW) == "You called 3 days ago and they did not pick up."
    assert reason(called, lang="es", now=NOW + timedelta(days=1)) == "Le llamaste hace 4 días y no contestó."
    voicemail = Signal(
        type="callback_no_answer",
        contact_id="42",
        deal_id=None,
        source_memo_id="memo-1",
        due_at=None,
        payload={"outcome": "voicemail", "at": (NOW - timedelta(days=2)).isoformat()},
        dedupe_key="callback:memo-1",
    )
    # "voicemail" is how the call ended, not a message the rep left: never claim one.
    assert reason(voicemail, lang="es", now=NOW) == "Saltó el buzón de voz hace 2 días. Vuelve a llamar."
    assert reason(voicemail, lang="en", now=NOW) == "It went to voicemail 2 days ago. Call again."
    assert "mensaje" not in reason(voicemail, lang="es", now=NOW)
    assert reason(called, lang="es", now=NOW - timedelta(days=2)) == "Le llamaste ayer y no contestó."
    assert reason(called, lang="es", now=NOW - timedelta(days=3)) == "Le llamaste hoy y no contestó."


def test_never_contacted_reason():
    signal = Signal(
        type="never_contacted",
        contact_id="42",
        deal_id=None,
        source_memo_id="",
        due_at=None,
        payload={},
        dedupe_key="never_contacted:crm-A:42",
    )
    assert reason(signal, lang="es") == "Nunca has hablado con este contacto."
    assert reason(signal, lang="en") == "You have never spoken with this contact."
