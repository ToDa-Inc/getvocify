"""Deterministic coaching lines for the rep's own daily / weekly report. Pure, no I/O.

Spanish plain text built only from step labels and counts: never a transcript quote."""

from __future__ import annotations

from app.services.coaching import rep_coaching as engine

BEST_MIN_APPLICABLE = 2
ON_TRACK_ES = "Vas bien: ningún paso del proceso se repite como fallo."


def _best_step(rates: list[dict]) -> dict | None:
    """Highest rate with at least 2 applicable; ties go to more applicable, then step order."""
    candidates = [(r["rate"], r["applicable"], -order, r) for order, r in enumerate(rates)
                  if r["applicable"] >= BEST_MIN_APPLICABLE and r["rate"] is not None]
    return max(candidates, key=lambda c: c[:3])[3] if candidates else None


def daily_coaching_line(day_rows: list[dict], steps: list[dict], focus: dict | None) -> str | None:
    """None when there was no conversation that day (no calls, no message).

    The daily report goes out at the end of the day it covers (due_sends: 18:00 local), so
    the line talks about "hoy" and the week's focus, never "ayer" or "mañana"."""
    conversations = [r for r in day_rows if r.get("is_conversation")]
    if not conversations:
        return None
    rates = engine.step_rates(conversations, steps)
    best = _best_step(rates)
    parts = []
    if best:
        parts.append(f"Lo mejor de hoy: {best['label']} en {best['done']} de {best['applicable']}.")
    if not focus:
        parts.append(ON_TRACK_ES)
        return " ".join(parts)
    own = next((r for r in rates if r["step_id"] == focus["step_id"]), None)
    today = f"hoy {own['done']} de {own['applicable']}" if own and own["applicable"] else "hoy sin datos"
    parts.append(f"Tu foco esta semana: {focus['label']} ({today}).")
    return " ".join(parts)


def _percent(rate: float | None) -> str:
    return "—" if rate is None else f"{round(rate * 100)}%"


def weekly_coaching_line(
    previous_focus: dict | None, week_rows: list[dict], steps: list[dict], new_focus: dict | None
) -> str | None:
    """previous_focus: last week's chosen focus (with its `rate` before). week_rows: the
    reported week, to see where that step ended. new_focus: chosen over the reported week."""
    if not any(r.get("is_conversation") for r in week_rows) and previous_focus is None and new_focus is None:
        return None
    parts = []
    if previous_focus:
        after = next((r for r in engine.step_rates(week_rows, steps) if r["step_id"] == previous_focus["step_id"]), None)
        parts.append(
            f"Foco de la semana pasada: {previous_focus['label']} "
            f"{_percent(previous_focus.get('rate'))}→{_percent(after['rate'] if after else None)}."
        )
    if new_focus:
        parts.append(f"Nuevo foco: {new_focus['label']}.")
    elif previous_focus:
        parts.append("Esta semana no hay un paso que se repita como fallo.")
    else:
        parts.append(ON_TRACK_ES)
    return " ".join(parts)
