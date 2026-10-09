"""Deterministic coaching lines: pure, Spanish, no transcript quotes."""

from app.services.coaching.rep_messages import daily_coaching_line, weekly_coaching_line

STEPS = [{"step_id": "open", "label": "Apertura"}, {"step_id": "pain", "label": "Dolor"}]
FOCUS = {"step_id": "open", "label": "Apertura", "rate": 0.4}


def _row(states, *, conversation=True):
    return {"is_conversation": conversation, "steps": [
        {"step_id": k, "label": k, "state": v, "quote": "SECRET quote"} for k, v in states.items()]}


def test_daily_best_step_and_focus_with_yesterdays_counts():
    rows = [_row({"open": "missing", "pain": "done"}), _row({"open": "done", "pain": "done"})]
    assert daily_coaching_line(rows, STEPS, FOCUS) == (
        "Lo mejor de hoy: Dolor en 2 de 2. Tu foco esta semana: Apertura (hoy 1 de 2)."
    )


def test_daily_without_focus_says_going_well():
    rows = [_row({"open": "done", "pain": "done"})] * 2
    assert daily_coaching_line(rows, STEPS, None).endswith("Vas bien: ningún paso del proceso se repite como fallo.")


def test_daily_no_conversations_means_no_message():
    assert daily_coaching_line([], STEPS, FOCUS) is None
    assert daily_coaching_line([_row({"open": "missing"}, conversation=False)], STEPS, FOCUS) is None


def test_daily_best_needs_two_applicable_and_focus_may_have_no_data():
    line = daily_coaching_line([_row({"pain": "done"})], STEPS, FOCUS)
    assert line == "Tu foco esta semana: Apertura (hoy sin datos)."


def test_lines_never_carry_quotes():
    rows = [_row({"open": "missing", "pain": "done"})] * 2
    assert "SECRET" not in daily_coaching_line(rows, STEPS, FOCUS)
    assert "SECRET" not in weekly_coaching_line(FOCUS, rows, STEPS, FOCUS)


def test_weekly_with_previous_and_new_focus():
    rows = [_row({"open": "done"}), _row({"open": "done"}), _row({"open": "done"}), _row({"open": "missing"})]
    new = {"step_id": "pain", "label": "Dolor", "rate": 0.2}
    assert weekly_coaching_line(FOCUS, rows, STEPS, new) == (
        "Foco de la semana pasada: Apertura 40%→75%. Nuevo foco: Dolor."
    )


def test_weekly_without_new_focus():
    rows = [_row({"open": "done"})] * 3
    assert weekly_coaching_line(FOCUS, rows, STEPS, None) == (
        "Foco de la semana pasada: Apertura 40%→100%. Esta semana no hay un paso que se repita como fallo."
    )


def test_weekly_first_week_has_only_the_new_focus():
    assert weekly_coaching_line(None, [_row({"open": "missing"})], STEPS, FOCUS) == "Nuevo foco: Apertura."
    assert weekly_coaching_line(None, [_row({"open": "done"})], STEPS, None).startswith("Vas bien")
