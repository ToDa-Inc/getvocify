"""F06: reasons stay short and come from one server-side writer."""

from datetime import datetime, timezone

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


def test_callback_no_answer_reason_names_the_outcome_and_days():
    called = Signal(
        type="callback_no_answer",
        contact_id="42",
        deal_id=None,
        source_memo_id="memo-1",
        due_at=None,
        payload={"outcome": "no_response", "days_since": 3},
        dedupe_key="callback:memo-1",
    )
    assert reason(called, lang="es") == "Le llamaste hace 3 días y no contestó."
    assert reason(called, lang="en") == "You called 3 days ago and they did not pick up."
    voicemail = Signal(
        type="callback_no_answer",
        contact_id="42",
        deal_id=None,
        source_memo_id="memo-1",
        due_at=None,
        payload={"outcome": "voicemail", "days_since": 2},
        dedupe_key="callback:memo-1",
    )
    assert "mensaje de voz" in reason(voicemail, lang="es")


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
