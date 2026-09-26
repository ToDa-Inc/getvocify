"""Render persisted snapshot metrics for email and in-app read paths."""

from __future__ import annotations

from html import escape

UNAVAILABLE_ES = "No disponible"

OBJECTION_LABELS_ES = {
    "price": "Precio",
    "timing": "Plazo",
    "authority": "Autoridad",
    "competitor": "Competidor",
    "status_quo": "Statu quo",
    "trust": "Confianza",
    "other": "Otra",
}


def metric_display(value: int | float | None, *, unavailable: str = UNAVAILABLE_ES) -> str:
    return unavailable if value is None else str(value)


def adherence_display(snapshot: dict, *, unavailable: str = UNAVAILABLE_ES) -> str:
    steps = snapshot.get("adherence_steps")
    if isinstance(steps, dict) and int(steps.get("applicable") or 0) > 0:
        return f"{int(steps.get('met') or 0)} de {int(steps['applicable'])} pasos"
    return metric_display((snapshot.get("metrics") or {}).get("adherence"), unavailable=unavailable)


def snapshot_metric_cells(snapshot: dict, *, unavailable: str = UNAVAILABLE_ES) -> dict[str, str]:
    metrics = snapshot.get("metrics") or {}
    return {
        "attempts": str(int(metrics.get("attempts") or 0)),
        "connected_calls": str(int(metrics.get("connected_calls") or 0)),
        "conversations": channels_text(snapshot) or str(int(metrics.get("connected_calls") or 0)),
        "meetings_agreed": str(int(metrics.get("meetings_agreed") or 0)),
        "deals_won": metric_display(metrics.get("deals_won"), unavailable=unavailable),
        "adherence": adherence_display(snapshot, unavailable=unavailable),
    }


def _count(value: int, singular: str, plural: str) -> str:
    return f"{value} {singular if value == 1 else plural}"


CHANNEL_WORDS_ES = (
    ("call", "llamada", "llamadas"),
    ("meeting", "reunión", "reuniones"),
    ("visit", "visita", "visitas"),
)


def channels_text(snapshot: dict) -> str | None:
    """«3 llamadas · 1 reunión · 2 visitas», channels above zero only. None for snapshots from before channels."""
    channels = (snapshot.get("metrics") or {}).get("channels")
    if not isinstance(channels, dict):
        return None
    parts = [
        _count(int(channels.get(key) or 0), singular, plural)
        for key, singular, plural in CHANNEL_WORDS_ES
        if int(channels.get(key) or 0) > 0
    ]
    return " · ".join(parts)


def summary_line(snapshot: dict) -> str:
    """One sentence of facts from the snapshot. No model, no judgement."""
    metrics = snapshot.get("metrics") or {}
    connected = int(metrics.get("connected_calls") or 0)
    meetings = int(metrics.get("meetings_agreed") or 0)
    if snapshot.get("scope") == "team":
        lead = "Tu equipo esta semana"
    elif snapshot.get("report_type") == "weekly":
        lead = "Esta semana"
    else:
        lead = "Hoy"
    channels = channels_text(snapshot)
    if channels is not None:
        return f"{lead}: {channels or 'sin conversaciones'}. {_count(meetings, 'reunión acordada', 'reuniones acordadas')}."
    return (
        f"{lead}: {_count(connected, 'llamada conectada', 'llamadas conectadas')} "
        f"y {_count(meetings, 'reunión acordada', 'reuniones acordadas')}."
    )


def email_subject(snapshot: dict) -> str:
    if snapshot.get("scope") == "team":
        return "Tu equipo esta semana"
    if snapshot.get("report_type") == "weekly":
        return "Tu semana en Vocify"
    return "Tu resumen de actividad"


def example_memo_paths(snapshot: dict) -> list[str]:
    examples = snapshot.get("examples") or []
    return [f"/dashboard/memos/{memo_id}" for memo_id in examples if memo_id]


def _objections_block(snapshot: dict) -> str:
    objections = snapshot.get("objections")
    if not isinstance(objections, list) or not objections:
        return ""
    rows = "".join(
        f"<tr><th>{escape(OBJECTION_LABELS_ES.get(str(item.get('name')), str(item.get('name'))))}</th>"
        f"<td>{int(item.get('count') or 0)}</td></tr>"
        for item in objections
    )
    return f"<p>Objeciones más frecuentes</p><table>{rows}</table>"


MONTHS_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic")
SAMPLE_NOTE_ES = "* Menos de cinco conversaciones puntuadas: sin conclusión."


def _week_label(iso_date: str) -> str:
    _, month, day = (int(part) for part in iso_date[:10].split("-"))
    return f"{day} {MONTHS_ES[month - 1]}"


def _trend_cell(cell: dict) -> str:
    if cell.get("state") == "gap":
        return "—"
    if cell.get("state") != "scored":
        return "Sin puntuar"
    mark = "*" if cell.get("sample_limited") else ""
    return f"{int(cell.get('met') or 0)} de {int(cell.get('applicable') or 0)}{mark}"


def _trend_block(snapshot: dict) -> str:
    trend = snapshot.get("adherence_trend")
    if not isinstance(trend, dict) or not trend.get("weeks"):
        return ""
    series = [("Equipo", trend.get("team") or [])] + [
        (str(rep.get("name") or ""), rep.get("weeks") or []) for rep in trend.get("reps") or []
    ]
    head = "<tr><th></th>" + "".join(f"<th>{_week_label(week)}</th>" for week in trend["weeks"]) + "</tr>"
    rows = "".join(
        f"<tr><th>{escape(name)}</th>" + "".join(f"<td>{_trend_cell(cell)}</td>" for cell in cells) + "</tr>"
        for name, cells in series
    )
    limited = any(cell.get("sample_limited") for _, cells in series for cell in cells)
    note = f"<p>{SAMPLE_NOTE_ES}</p>" if limited else ""
    return f"<p>Adherencia por semana</p><table>{head}{rows}</table>{note}"


def email_html_for_snapshot(snapshot: dict, *, report_id: str, app_origin: str = "https://app.getvocify.com") -> str:
    cells = snapshot_metric_cells(snapshot)
    origin = app_origin.rstrip("/")
    report_href = f"{origin}/dashboard/reports/{report_id}"
    rows = "".join(
        f"<tr><th>{label}</th><td>{cells[key]}</td></tr>"
        for label, key in (
            ("Intentos", "attempts"),
            ("Conversaciones", "conversations"),
            ("Reuniones acordadas", "meetings_agreed"),
            ("Cierres", "deals_won"),
            ("Adherencia", "adherence"),
        )
    )
    links = "".join(f'<li><a href="{origin}{path}">{path}</a></li>' for path in example_memo_paths(snapshot))
    examples_block = f"<ul>{links}</ul>" if links else ""
    coaching = snapshot.get("coaching")
    coaching_block = f"<p>{coaching}</p>" if isinstance(coaching, str) and coaching.strip() else ""
    return (
        f"<p>{summary_line(snapshot)}</p>"
        f"<table>{rows}</table>"
        f"{_trend_block(snapshot)}"
        f"{_objections_block(snapshot)}"
        f"{coaching_block}"
        f"{examples_block}"
        f"<p><a href=\"{report_href}\">Ver informe</a></p>"
    )
