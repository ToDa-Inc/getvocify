"""A step keeps its history while its criterion stays; a changed criterion starts from zero."""

from app.services.coaching.rep_coaching import interaction_row, step_rates
from app.services.playbooks.insights import step_insights
from app.services.playbooks.step_identity import StepMatcher, criterion_key

PAIN = "Pregunta cómo captan clientes hoy y qué les cuesta."
LIVE = [
    {"step_id": "descubrir_pain", "label": "Descubrir el pain", "criterion": PAIN},
    {"step_id": "datos", "label": "Datos de la empresa", "criterion": "Saca al menos tres datos de la empresa."},
]


def test_criterion_key_ignores_case_spacing_and_the_closing_stop():
    assert criterion_key("  Pregunta  cómo captan clientes HOY y qué les cuesta ") == criterion_key(PAIN)
    assert criterion_key(None) == ""


def test_same_id_same_criterion_counts():
    assert StepMatcher(LIVE).match("descubrir_pain", PAIN) == "descubrir_pain"


def test_renamed_step_with_the_same_criterion_keeps_its_history():
    # Republished from the AI structurer: new ids, same criterion.
    assert StepMatcher(LIVE).match("pain", PAIN) == "descubrir_pain"


def test_changed_criterion_starts_from_zero():
    matcher = StepMatcher(LIVE)
    assert matcher.match("datos", "Saca dos datos de la empresa.") is None
    assert matcher.match("borrado", "Un paso que ya no existe.") is None


def test_a_verdict_stored_without_its_criterion_falls_back_to_the_id():
    matcher = StepMatcher(LIVE)
    assert matcher.match("datos") == "datos"
    assert matcher.match("otro") is None


def _memo(observations, memo_id="m1"):
    return {
        "id": memo_id, "user_id": "u1", "sales_motion_key": "discovery", "screening_outcome": "connected",
        "audio_duration": 120, "rep_outcome": None, "capture_started_at": "2026-10-06T10:00:00+00:00",
        "created_at": "2026-10-06T10:00:00+00:00",
        "extraction": {"summary": "", "intelligence": {"playbook_observations": observations}},
    }


def _obs(step_id, criterion, status):
    return {"step_id": step_id, "label": step_id, "criterion": criterion, "status": status}


# Two calls judged on the previous version: the pain step had another id, the data step another criterion.
OLD_CALLS = [
    _memo([_obs("pain", PAIN, "missed"), _obs("datos", "Saca dos datos de la empresa.", "met")], "m1"),
    _memo([_obs("pain", PAIN, "met"), _obs("datos", "Saca dos datos de la empresa.", "met")], "m2"),
]


def test_rep_rates_after_a_republish():
    rows = [interaction_row(memo) for memo in OLD_CALLS]
    rates = {r["step_id"]: r for r in step_rates(rows, LIVE)}
    assert (rates["descubrir_pain"]["done"], rates["descubrir_pain"]["applicable"]) == (1, 2)
    assert rates["datos"]["applicable"] == 0  # criterion changed: from zero
    # The call's own history keeps what it was judged on.
    assert [s["step_id"] for s in rows[0]["steps"]] == ["pain", "datos"]


def test_head_of_sales_step_insights_after_a_republish():
    by_step = {s["step_id"]: s for s in step_insights(OLD_CALLS, LIVE)}
    assert (by_step["descubrir_pain"]["met"], by_step["descubrir_pain"]["missed"]) == (1, 1)
    assert (by_step["datos"]["met"], by_step["datos"]["missed"]) == (0, 0)


def test_two_old_steps_landing_on_one_live_step_count_once_per_call():
    memo = _memo([_obs("pain", PAIN, "met"), _obs("pain_2", PAIN, "missed")])
    rates = {r["step_id"]: r for r in step_rates([interaction_row(memo)], LIVE)}
    assert (rates["descubrir_pain"]["done"], rates["descubrir_pain"]["applicable"]) == (1, 1)
